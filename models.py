from sqlalchemy import Column, ForeignKey, Integer, String, Text

from db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password = Column(String(100), nullable=False)


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    resume_text = Column(Text, nullable=False)
    result = Column(Text, nullable=False)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(120), nullable=False)
    description = Column(Text, nullable=False, default="")
    technologies = Column(String(500), nullable=False, default="")
    repository_url = Column(String(500), nullable=False, default="")
    demo_url = Column(String(500), nullable=False, default="")
    status = Column(String(20), nullable=False, default="planned")
