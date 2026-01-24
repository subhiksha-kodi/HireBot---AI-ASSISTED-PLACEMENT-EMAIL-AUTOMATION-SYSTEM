from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Date

from app.db.base import Base


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    roll_no = Column(String(50), index=True, nullable=False)
    name = Column(String(255), nullable=False)
    department = Column(String(255), nullable=False)
    domain = Column(String(255), nullable=False)
    cgpa = Column(Float, nullable=False)
    ps_level = Column(Float, nullable=False)  # Programming Skill Level (Weighted Score)
    skills_text = Column(String(500), nullable=True) # Raw skills string (e.g., "python-4, java-3")
    import_order = Column(Integer, default=0) # Order from CSV file
    organization = Column(String(255), nullable=True)
    date = Column(Date, nullable=True)  # Date column for duplicate handling
    created_at = Column(DateTime, default=datetime.utcnow)


