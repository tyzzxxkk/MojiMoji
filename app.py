from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime # 날짜 저장용
import json
import os
import random # JSON, 경로, 랜덤 섞기

app = Flask(__name__)
app.secret_key = "change-this"

# DB 연결
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://moji:1120@localhost:3306/mojimoji?charset=utf8mb4"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 280}

db = SQLAlchemy(app)

# DB 모델
class User(db.Model):
    __tablename__ = "users"   # users 테이블로 저장
    id = db.Column(db.Integer, primary_key=True)      # 회원 고유 번호(PK)
    username = db.Column(db.String(40), unique=True)  # 아이디
    password_hash = db.Column(db.String(255))         # 암호화된 비밀번호
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # 가입 날짜

class Result(db.Model):
    __tablename__ = "results"   # results 테이블
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))  # users.id 참조
    category = db.Column(db.String(20))     # 카테고리(드라마/영화/노래/예능)

    score = db.Column(db.Integer)           # 문제 맞추고 얻은 점수
    total_questions = db.Column(db.Integer, default=0)  # 전체 문제 수
    hints_used = db.Column(db.Integer, default=0)       # 사용한 힌트 수
    created_at = db.Column(db.DateTime, default=datetime.utcnow) # 게임 플레이 날짜

    # User 테이블과 연결해 user.results 형태로 접근 가능
    user = db.relationship("User", backref=db.backref("results", lazy=True))
    
# JSON 문제 로드
def load_questions(category):
    # 현재 app.py가 있는 경로를 기준으로 data/카테고리.json 파일을 불러온다
    base_path = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(base_path, "data", f"{category}.json")

    # 파일 자체가 없다면 오류 대신 빈 리스트 반환
    if not os.path.exists(filepath):
        print("❌ JSON 없음:", filepath)
        return []

    # JSON 파일 열어 해당 카테고리 배열을 반환
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get(category, [])
    
# 기본 페이지
@app.route("/")
def home():
    return render_template("index.html") # 시작 화면

# 회원가입
@app.route("/auth/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # 사용자가 입력한 아이디/비밀번호 값 가져오기
        username = request.form["username"].strip()
        password = request.form["password"]
        confirm = request.form["password_confirm"]

        # 비밀번호 확인 값 다르면 회원가입 실패
        if password != confirm:
            flash("비밀번호가 일치하지 않습니다.", "error")
            return redirect(url_for("register"))

        # 이미 존재하는 아이디인지 검사
        if User.query.filter_by(username=username).first():
            flash("이미 존재하는 아이디입니다.", "error")
            return redirect(url_for("register"))

        # 새로운 회원 생성 후 저장
        new_user = User(username=username,
                        password_hash=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()

        flash("회원가입 성공! 로그인 해주세요.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

# 로그인
@app.route("/auth/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        # 해당 아이디가 존재하는지 확인
        user = User.query.filter_by(username=username).first()

        # 아이디 없거나 비밀번호 틀리면 실패
        if not user or not check_password_hash(user.password_hash, password):
            flash("아이디 또는 비밀번호가 올바르지 않습니다.", "error")
            return redirect(url_for("login"))

        # 세션에 사용자 정보 저장하여 로그인 유지
        session["user_id"] = user.id
        session["username"] = user.username

        flash(f"{user.username}님 환영합니다!", "success")
        return redirect(url_for("game_select"))

    return render_template("login.html")

# 로그아웃
@app.route("/logout")
def logout():
    session.clear()
    flash("로그아웃 되었습니다.", "success")
    return redirect(url_for("home"))

# 게임 선택 화면
@app.route("/game_select")
def game_select():
    # 로그인 안 돼 있으면 접근 불가
    if "user_id" not in session:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login"))

    return render_template("game_select.html", username=session.get("username"))

# 퀴즈 시작 (랜덤 셔플)
@app.route("/quiz/<category>")
def quiz(category):
    # 로그인 확인
    if "user_id" not in session:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login"))

    # 유효한 카테고리인지 검사
    valid_categories = ["movie", "drama", "song", "tv_program"]
    if category not in valid_categories:
        flash("잘못된 카테고리입니다.", "error")
        return redirect(url_for("game_select"))

    # 문제 JSON 로드
    questions = load_questions(category)

    # 문제 번호를 랜덤하게 셔플하여 문제 출제 순서 만듦
    order = list(range(len(questions)))
    random.shuffle(order)

    # 현재 플레이 상태를 세션에 저장
    session["quiz_category"] = category
    session["order"] = order
    session["question_index"] = 0
    session["score"] = 10
    session["hints_used"] = 0
    session["current_hint_index"] = 0
    session["attempts"] = 0

    # 첫 문제 전달
    first_q = questions[order[0]] if questions else {}

    return render_template(
        "quiz.html",
        category=category,
        username=session.get("username"),
        first_question=first_q,
        total_questions=len(questions)
    )
    
# 문제 가져오기
@app.route("/api/get_question")
def get_question():
    category = session.get("quiz_category")
    index = session.get("question_index", 0)
    order = session.get("order", [])

    questions = load_questions(category)

    if index >= len(order):
        return jsonify({"finished": True})  # 모든 문제를 다 풀면 finished 반환

    q = questions[order[index]]  # 현재 문제 정보

    return jsonify({
        "emoji_hint": q["emoji_hint"], # 이모지 힌트
        "score": session.get("score", 10),
        "hints_used": session.get("hints_used", 0)
    })
    
# 정답 체크
@app.route("/api/check_answer", methods=["POST"])
def check_answer():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401 # 로그인 안 되어 있으면 진행 불가

    data = request.get_json()
    user_answer = data.get("answer", "").strip().lower()   # strip() 사용!!! 절대 trim() 쓰면 안됨

    category = session.get("quiz_category")
    index = session.get("question_index", 0)
    order = session.get("order", [])
    questions = load_questions(category)

    question = questions[order[index]]
    correct_answer = question["answer"]

    # 정답이 리스트일 수도 있기 때문에 통일된 리스트 형태로 변환
    if isinstance(correct_answer, list):
        correct_list = [x.lower().strip() for x in correct_answer]
    else:
        correct_list = [correct_answer.lower().strip()]

    attempts = session.get("attempts", 0)
    score = session.get("score", 10)

    attempts += 1
    session["attempts"] = attempts

    # PASS 기능 ("끝", "pass", "패스" → 바로 다음 문제)
    if user_answer in ["끝", "pass", "패스"]:
        session["question_index"] = index + 1
        session["attempts"] = 0
        session["hints_used"] = 0
        session["current_hint_index"] = 0

        # 마지막 문제인지 확인하고 종료
        if session["question_index"] >= len(questions):
            return jsonify({
                "correct": False,
                "finished": True,
                "message": "마지막 문제입니다!"
            })

        return jsonify({
            "correct": False,
            "next_question": True,
            "message": "다음 문제로 넘어갑니다!"
        })

    # 정답
    if user_answer in correct_list:

        # 점수 저장 (누적 점수 모드)
        result = Result(
            user_id=session["user_id"],
            category=category,
            score=session["score"],
            total_questions=len(questions),
            hints_used=session.get("hints_used", 0)
        )
        db.session.add(result)
        db.session.commit()

        # 다음 문제로 이동
        session["question_index"] = index + 1
        session["attempts"] = 0
        session["hints_used"] = 0
        session["current_hint_index"] = 0

        if session["question_index"] >= len(questions):
            # 마지막 문제 정답 → 게임 종료
            return jsonify({"correct": True, "finished": True, "final_score": score})

        return jsonify({"correct": True, "finished": False, "score": score})

    # 오답
    max_attempts = 10

    if attempts >= max_attempts:
        # 마지막 문제 정답 → 게임 종료
        session["question_index"] = index + 1
        session["attempts"] = 0
        session["hints_used"] = 0
        session["current_hint_index"] = 0

        return jsonify({
            "correct": False,
            "next_question": True,
            "message": f'정답은 "{correct_list[0]}" 이었습니다.',
            "score": score
        })
        
    # 아직 시도 가능 → 오답만 알려줌
    return jsonify({
        "correct": False,
        "attempts_left": max_attempts - attempts,
        "score": score
    })

# 힌트
@app.route("/api/get_hint", methods=["POST"])
def get_hint():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    category = session.get("quiz_category")
    index = session.get("question_index", 0)
    order = session.get("order", [])
    questions = load_questions(category)

    question = questions[order[index]]
    hints = question.get("hints", [])

    used = session.get("hints_used", 0)
    current_index = session.get("current_hint_index", 0)

    if used >= 5:
        # 힌트는 최대 5개만 사용 가능
        return jsonify({"error": "힌트를 모두 사용했습니다."}), 400

    if current_index >= len(hints):
        # 더 이상 제공할 힌트가 없을 때
        return jsonify({"error": "더 이상 힌트가 없습니다."}), 400

    hint = hints[current_index]
    
    used += 1
    session["hints_used"] = used
    session["current_hint_index"] = current_index + 1
    
    # ⭐ 새로운 점수 규칙 적용
    hint_score_table = {
        0: 10,
        1: 9,
        2: 8,
        3: 6,
        4: 3,
        5: 1
    }
    
    new_score = hint_score_table.get(used, 1)
    session["score"] = new_score

    return jsonify({
        "hint": hint,
        "hints_used": used,
        "score": new_score
    })

# 랭킹
@app.route("/ranking")
def ranking():

    # 전체 랭킹 (모든 카테고리 포함)
    ranking_all = (
        db.session.query(
            User.username.label("username"),
            Result.category.label("category"),
            db.func.SUM(Result.score).label("total_score"),
            db.func.MAX(Result.created_at).label("last_play"),
        )
        .join(User, User.id == Result.user_id)
        .group_by(User.username, Result.category)
        .order_by(db.desc("total_score"))
        .all()
    )

    # 카테고리 리스트
    categories = ["drama", "movie", "song", "tv_program"]

    # 카테고리별 랭킹을 저장할 딕셔너리
    ranking_by_category = {}

    for cat in categories:
        # 카테고리별 유저 점수 총합 계산
        rows = (
            db.session.query(
                User.username.label("username"),
                db.func.SUM(Result.score).label("total_score"),
                db.func.MAX(Result.created_at).label("last_play"),
            )
            .join(User, User.id == Result.user_id)
            .filter(Result.category == cat)
            .group_by(User.username)
            .order_by(db.desc("total_score"))
            .all()
        )
        ranking_by_category[cat] = rows

    # 랭킹 템플릿에 전체/카테고리별 결과 전달
    return render_template(
        "ranking.html",
        ranking_all=ranking_all,
        ranking_by_category=ranking_by_category
    )
    
# 실행
if __name__ == "__main__":
    with app.app_context():
        db.create_all() # DB 테이블이 없으면 자동 생성

    app.run(debug=True)