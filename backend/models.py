from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Table
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

# Association table for the many-to-many relationship between users and posts (interactions)
interactions = Table(
    "interactions",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True),
    Column("post_id", Integer, ForeignKey("posts.post_id", ondelete="CASCADE"), primary_key=True),
)

class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    password_reset: Mapped["PasswordReset"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    admin_logs: Mapped[list["AdminLog"]] = relationship(back_populates="admin", cascade="all, delete-orphan")
    user_skills: Mapped[list["UserSkill"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    posts: Mapped[list["Post"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    interacted_posts: Mapped[list["Post"]] = relationship(secondary=interactions, back_populates="interacted_users")


class PasswordReset(Base):
    __tablename__ = "password_resets"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    reset_code: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    user: Mapped["User"] = relationship(back_populates="password_reset")


class AdminLog(Base):
    __tablename__ = "admin_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(20))
    target_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    admin: Mapped["User"] = relationship(back_populates="admin_logs")


class Skill(Base):
    __tablename__ = "skills"

    skill_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    skill_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="Uncategorized")

    modules: Mapped[list["SkillModule"]] = relationship(back_populates="skill", cascade="all, delete-orphan")
    user_skills: Mapped[list["UserSkill"]] = relationship(back_populates="skill", cascade="all, delete-orphan")


class UserSkill(Base):
    __tablename__ = "user_skills"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[int] = mapped_column(Integer, ForeignKey("skills.skill_id", ondelete="CASCADE"), primary_key=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    legacy_progress: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped["User"] = relationship(back_populates="user_skills")
    skill: Mapped["Skill"] = relationship(back_populates="user_skills")


class SkillModule(Base):
    __tablename__ = "skill_modules"

    module_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    skill_id: Mapped[int] = mapped_column(Integer, ForeignKey("skills.skill_id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)

    skill: Mapped["Skill"] = relationship(back_populates="modules")
    lessons: Mapped[list["LearningLesson"]] = relationship(cascade="all, delete-orphan")
    questions: Mapped[list["AssessmentQuestion"]] = relationship(cascade="all, delete-orphan")
    attempts: Mapped[list["AssessmentAttempt"]] = relationship(cascade="all, delete-orphan")
    completions: Mapped[list["ModuleCompletion"]] = relationship(cascade="all, delete-orphan")


class LearningLesson(Base):
    __tablename__ = "learning_lessons"

    lesson_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    module_id: Mapped[int] = mapped_column(Integer, ForeignKey("skill_modules.module_id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class AssessmentQuestion(Base):
    __tablename__ = "assessment_questions"

    question_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    module_id: Mapped[int] = mapped_column(Integer, ForeignKey("skill_modules.module_id", ondelete="CASCADE"), nullable=False)
    question_number: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    option_a: Mapped[str] = mapped_column(Text, nullable=False)
    option_b: Mapped[str] = mapped_column(Text, nullable=False)
    option_c: Mapped[str] = mapped_column(Text, nullable=False)
    option_d: Mapped[str] = mapped_column(Text, nullable=False)
    correct_option: Mapped[str] = mapped_column(String(1), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AssessmentAttempt(Base):
    __tablename__ = "assessment_attempts"

    attempt_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    module_id: Mapped[int] = mapped_column(Integer, ForeignKey("skill_modules.module_id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    current_difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    questions_answered: Mapped[int] = mapped_column(Integer, default=0)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0)
    score_percentage: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssessmentAttemptQuestion(Base):
    __tablename__ = "assessment_attempt_questions"

    attempt_id: Mapped[int] = mapped_column(Integer, ForeignKey("assessment_attempts.attempt_id", ondelete="CASCADE"), primary_key=True)
    question_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("assessment_questions.question_id", ondelete="CASCADE"), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)


class AssessmentAttemptAnswer(Base):
    __tablename__ = "assessment_attempt_answers"

    attempt_id: Mapped[int] = mapped_column(Integer, ForeignKey("assessment_attempts.attempt_id", ondelete="CASCADE"), primary_key=True)
    question_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("assessment_questions.question_id", ondelete="CASCADE"), nullable=False)
    selected_option: Mapped[str] = mapped_column(String(1), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ModuleCompletion(Base):
    __tablename__ = "module_completions"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    module_id: Mapped[int] = mapped_column(Integer, ForeignKey("skill_modules.module_id", ondelete="CASCADE"), primary_key=True)
    completed_attempt_id: Mapped[int] = mapped_column(Integer, ForeignKey("assessment_attempts.attempt_id", ondelete="CASCADE"), unique=True, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Post(Base):
    __tablename__ = "posts"

    post_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=True)

    owner: Mapped["User"] = relationship(back_populates="posts")
    interacted_users: Mapped[list["User"]] = relationship(secondary=interactions, back_populates="interacted_posts")