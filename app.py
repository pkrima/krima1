import json

import os

import secrets

from urllib.parse import urlparse



import docx

import PyPDF2

from flask import Flask, flash, redirect, render_template, request, send_from_directory, session, url_for

from werkzeug.security import check_password_hash, generate_password_hash



import models

from ai import analyze_resume, _get_config_value

from db import Base, SessionLocal, engine



app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)



Base.metadata.create_all(bind=engine)





@app.route("/style.css")

def stylesheet():

    return send_from_directory(app.template_folder, "style.css", mimetype="text/css", max_age=0)





def hash_password(password):

    return generate_password_hash(password, method="pbkdf2:sha256:600000", salt_length=8)





PROJECT_STATUSES = {

    "planned": "Planned",

    "in_progress": "In progress",

    "completed": "Completed",

}





def valid_project_url(value):

    if not value:

        return True

    parsed = urlparse(value)

    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)





@app.route("/")

def home():

    if "user" in session:

        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))





@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email or len(password) < 8:
            flash("Enter a valid email and a password of at least 8 characters.", "error")
            return render_template("signup.html"), 400

        db = SessionLocal()
        try:
            existing_user = db.query(models.User).filter_by(email=email).first()
            if existing_user:
                flash("An account with that email already exists. Please log in.", "error")
                return render_template("signup.html"), 409

            db.add(models.User(email=email, password=hash_password(password)))
            db.commit()
        finally:
            db.close()

        flash("Your account is ready. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])

def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()

        password = request.form.get("password", "")



        db = SessionLocal()

        try:

            user = db.query(models.User).filter_by(email=email).first()

            if user:

                valid_password = check_password_hash(user.password, password)

                if not valid_password and user.password == password:

                    user.password = hash_password(password)

                    db.commit()

                    valid_password = True

                if valid_password:

                    session["user"] = user.email

                    return redirect(url_for("dashboard"))

        finally:

            db.close()



        flash("Invalid email or password. Please try again.", "error")

    return render_template("login.html")





@app.route("/dashboard", methods=["GET", "POST"])

def dashboard():

    if "user" not in session:

        return redirect(url_for("login"))



    result = None

    if request.method == "POST":

        user_goal = request.form.get("role", "").strip()

        resume_text = request.form.get("resume_text", "").strip()

        uploaded_file = request.files.get("resume_file")



        if uploaded_file and uploaded_file.filename:

            extension = uploaded_file.filename.rsplit(".", 1)[-1].lower()

            try:

                if extension == "pdf":

                    reader = PyPDF2.PdfReader(uploaded_file)

                    resume_text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()

                elif extension == "docx":

                    document = docx.Document(uploaded_file)

                    resume_text = "\n".join(paragraph.text for paragraph in document.paragraphs).strip()

                else:

                    raise ValueError("Please upload a PDF or DOCX resume.")

            except Exception as exc:

                result = {"error": f"Could not read the uploaded resume: {exc}"}



        if result is None and (not resume_text or not user_goal):

            result = {"error": "Provide your resume and the role you are targeting."}



        if result is None:

            db = SessionLocal()

            try:

                user = db.query(models.User).filter_by(email=session["user"]).first()

                if user is None:

                    session.pop("user", None)

                    return redirect(url_for("login"))



                result = analyze_resume(resume_text, user_goal)

                db.add(

                    models.Report(

                        user_id=user.id,

                        resume_text=resume_text,

                        result=json.dumps(result),

                    )

                )

                db.commit()

            except Exception as exc:

                db.rollback()

                result = {"error": f"Resume analysis failed: {exc}"}

            finally:

                db.close()



    if result is None and request.method == "GET":
        db = SessionLocal()
        try:
            user = db.query(models.User).filter_by(email=session["user"]).first()
            if user:
                latest_report = (
                    db.query(models.Report)
                    .filter_by(user_id=user.id)
                    .order_by(models.Report.id.desc())
                    .first()
                )
                if latest_report:
                    try:
                        result = json.loads(latest_report.result)
                    except json.JSONDecodeError:
                        result = None
        finally:
            db.close()
    gemini_key = _get_config_value("GEMINI_API_KEY") or _get_config_value("GOOGLE_API_KEY")
    api_active = bool(gemini_key)
    return render_template("dashboard.html", user=session["user"], result=result, api_active=api_active)


@app.route("/save-api-key", methods=["POST"])
def save_api_key():
    if "user" not in session:
        return redirect(url_for("login"))
    gemini_key = request.form.get("gemini_api_key", "").strip()
    if not gemini_key:
        flash("Please enter a valid Gemini API key.", "error")
        return redirect(url_for("dashboard"))

    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    lines = []
    found_key = False
    found_demo = False
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.startswith("GEMINI_API_KEY="):
            new_lines.append(f"GEMINI_API_KEY={gemini_key}\n")
            found_key = True
        elif line.startswith("DEMO_MODE="):
            new_lines.append("DEMO_MODE=false\n")
            found_demo = True
        else:
            new_lines.append(line)

    if not found_key:
        new_lines.insert(0, f"GEMINI_API_KEY={gemini_key}\n")
    if not found_demo:
        new_lines.append("DEMO_MODE=false\n")

    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    flash("Google Gemini API is now active on your project!", "success")
    return redirect(url_for("dashboard"))





@app.route("/history")

def history():

    if "user" not in session:

        return redirect(url_for("login"))



    db = SessionLocal()

    try:

        user = db.query(models.User).filter_by(email=session["user"]).first()

        if user is None:

            session.pop("user", None)

            return redirect(url_for("login"))



        reports = db.query(models.Report).filter_by(user_id=user.id).order_by(models.Report.id.desc()).all()

        parsed_reports = []

        for report in reports:

            try:

                result = json.loads(report.result)

            except json.JSONDecodeError:

                result = {"error": "This saved analysis could not be read."}

            parsed_reports.append({"resume": report.resume_text, "result": result})

    finally:

        db.close()

    return render_template("history.html", reports=parsed_reports)





@app.route("/projects", methods=["GET", "POST"])

def projects():

    if "user" not in session:

        return redirect(url_for("login"))



    db = SessionLocal()

    try:

        user = db.query(models.User).filter_by(email=session["user"]).first()

        if user is None:

            session.pop("user", None)

            return redirect(url_for("login"))



        if request.method == "POST":

            title = request.form.get("title", "").strip()

            description = request.form.get("description", "").strip()

            technologies = request.form.get("technologies", "").strip()

            repository_url = request.form.get("repository_url", "").strip()

            demo_url = request.form.get("demo_url", "").strip()



            if not title or len(title) > 120:

                flash("Enter a project name up to 120 characters.", "error")

            elif len(description) > 5000 or len(technologies) > 500:

                flash("Description or technologies exceed the allowed length.", "error")

            elif len(repository_url) > 500 or len(demo_url) > 500:

                flash("Project links must be 500 characters or fewer.", "error")

            elif not valid_project_url(repository_url) or not valid_project_url(demo_url):

                flash("Project links must use a valid http:// or https:// address.", "error")

            else:

                db.add(

                    models.Project(

                        user_id=user.id,

                        title=title,

                        description=description,

                        technologies=technologies,

                        repository_url=repository_url,

                        demo_url=demo_url,

                    )

                )

                db.commit()

                flash("Project added to your portfolio.", "success")

                return redirect(url_for("projects"))



        project_list = (

            db.query(models.Project)

            .filter_by(user_id=user.id)

            .order_by(models.Project.id.desc())

            .all()

        )

        return render_template(

            "projects.html",

            projects=project_list,

            statuses=PROJECT_STATUSES,

        )

    finally:

        db.close()





@app.route("/projects/<int:project_id>/status", methods=["POST"])

def update_project_status(project_id):

    if "user" not in session:

        return redirect(url_for("login"))



    status = request.form.get("status", "")

    if status not in PROJECT_STATUSES:

        flash("Choose a valid project status.", "error")

        return redirect(url_for("projects"))



    db = SessionLocal()

    try:

        user = db.query(models.User).filter_by(email=session["user"]).first()

        project = None

        if user is not None:

            project = db.query(models.Project).filter_by(id=project_id, user_id=user.id).first()

        if project is None:

            flash("Project not found.", "error")

            return redirect(url_for("projects"))



        project.status = status

        db.commit()

        flash("Project status updated.", "success")

        return redirect(url_for("projects"))

    finally:

        db.close()





@app.route("/projects/<int:project_id>/delete", methods=["POST"])

def delete_project(project_id):

    if "user" not in session:

        return redirect(url_for("login"))



    db = SessionLocal()

    try:

        user = db.query(models.User).filter_by(email=session["user"]).first()

        project = None

        if user is not None:

            project = db.query(models.Project).filter_by(id=project_id, user_id=user.id).first()

        if project is None:

            flash("Project not found.", "error")

            return redirect(url_for("projects"))



        db.delete(project)

        db.commit()

        flash("Project removed from your portfolio.", "success")

        return redirect(url_for("projects"))

    finally:

        db.close()





@app.route("/logout")

def logout():

    session.pop("user", None)

    return redirect(url_for("login"))





if __name__ == "__main__":

    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")

