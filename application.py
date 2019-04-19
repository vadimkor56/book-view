import os
import re
import requests
from werkzeug.security import generate_password_hash, check_password_hash

from flask import redirect, url_for, request, jsonify
from flask import Flask, session, render_template
from flask_session import Session
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import scoped_session, sessionmaker

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
	raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))


@app.route("/")
def index():
	return render_template("index.html")


@app.route('/login', methods=['GET', 'POST'])
def login():
	alert = None
	if request.method == 'POST':
		password = request.form['password-input']
		email = request.form['email-input']
		if (db.execute("SELECT * FROM users WHERE email = :email", {"email": email}).rowcount != 0):
			user = db.execute("SELECT * FROM users WHERE email = :email", {"email": email}).fetchone()
			if not (check_password_hash(user['password'], password)):
				alert = "wrong-password"
				return render_template('login.html', alert=alert, email=email)
			else:
				session['user_id'] = user['id']
				session['logged_in'] = True
				return redirect('/home')
		else:
			alert = "no-user"
			return render_template('login.html', alert=alert, email=email)
	return render_template('login.html', alert=alert, email="")


@app.route('/signup', methods=['GET', 'POST'])
def signup():
	alert = None
	if request.method == 'POST':
		password = request.form['password-input']
		email = request.form['email-input']
		if (db.execute("SELECT * FROM users WHERE email = :email", {"email": email}).rowcount != 0):
			alert = "user-exists"
			return render_template('signup.html', alert=alert, email=email)
		elif (len(password) < 8 or not re.search("[a-z]", password) or not re.search("[0-9]",
																					 password) or not re.search(
			"[A-Z]", password)):
			alert = "warning"
			return render_template('signup.html', alert=alert, email=email)
		else:
			alert = "success"
			hash_password = generate_password_hash(password)
			db.execute("INSERT INTO users (email, password) VALUES (:email, :password)",
					   {"email": email, "password": hash_password})
			db.commit()
			return render_template('signup.html', alert=alert, email="")
	return render_template('signup.html', alert=alert, email="")


@app.route("/home", methods=['GET', 'POST'])
def home():
	if request.method == 'POST':
		if ('logout' in request.form):
			session['logged_in'] = False
			return redirect("/")
		if ('search' in request.form):
			search = request.form['search'].title()
			if (search != ""):
				isbns = db.execute("select * from books where isbn like '%{search}%'".format(search=search)).fetchall()
				titles = db.execute(
					"select * from books where title like '%{search}%'".format(search=search)).fetchall()
				authors = db.execute(
					"select * from books where author like '%{search}%'".format(search=search)).fetchall()

				return render_template("home.html", isbns=isbns, titles=titles, authors=authors, books="")
			else:
				books = db.execute("select * from books").fetchall()
				return render_template("home.html", books=books)
	elif ('logged_in' in session and session['logged_in']):
		books = db.execute("select * from books").fetchall()
		#
		# The code below is for updating database with the info about books from goodreads
		#
		# for book in books:
		# 	try:
		# 		res = requests.get("https://www.goodreads.com/book/review_counts.json",
		# 						   params={"key": "ST2RJ5AgMF97gZU6Wj8zlw", "isbns": book.isbn}).json()
		# 		avg_rating = res['books'][0]['average_rating']
		# 		ratings_count = res['books'][0]['work_ratings_count']
		# 		db.execute("update books set review_count=:ratings_count, average_score=:avg_rating where isbn=:isbn",
		# 				   {"ratings_count": ratings_count, "avg_rating": avg_rating, "isbn": book.isbn})
		# 		db.commit()
		# 	except Exception:
		# 		pass
		return render_template("home.html", books=books)
	else:
		return redirect('/')


@app.route("/home/<int:book_id>", methods=['GET', 'POST'])
def book(book_id):
	reviews = db.execute("select * from reviews where book_id=:book_id", {"book_id": book_id}).fetchall()
	user_review = db.execute("select * from reviews where book_id=:book_id and user_id=:user_id",
							 {"book_id": book_id, "user_id": session['user_id']}).fetchone()
	if request.method == 'POST':
		if ('logout' in request.form):
			session['logged_in'] = False
			return redirect("/")
		if ('search' in request.form):
			search = request.form['search'].title()
			if (search != ""):
				isbns = db.execute("select * from books where isbn like '%{search}%'".format(search=search)).fetchall()
				titles = db.execute(
					"select * from books where title like '%{search}%'".format(search=search)).fetchall()
				authors = db.execute(
					"select * from books where author like '%{search}%'".format(search=search)).fetchall()
				return render_template("home.html", isbns=isbns, titles=titles, authors=authors, books="")
			else:
				books = db.execute("select * from books").fetchall()
				return render_template("home.html", books=books)
		elif ('rate' in request.form):
			rate = int(request.form['rate'])
			review = request.form['review'] if request.form['review'] != "" else None

			if (review):
				if (user_review == None):
					db.execute(
						"insert into reviews (book_id, user_id, rate, review) values (:book_id, :user_id, :rate, :review)",
						{"book_id": book_id, "user_id": session['user_id'], "rate": rate, "review": review})
					book = db.execute("select * from books where id=:book_id", {"book_id": book_id}).fetchone()
					average_score_bv = float(book['average_score_bv'])
					review_count_bv = int(book['review_count_bv'])

					average_score_bv = (review_count_bv * average_score_bv + rate) / (review_count_bv + 1)
					db.execute(
						"update books set average_score_bv=:average_score_bv, review_count_bv=:review_count_bv where id=:book_id",
						{"average_score_bv": average_score_bv, "review_count_bv": review_count_bv + 1,
						 "book_id": book_id})
				else:
					db.execute(
						"update reviews set rate=:rate, review=:review where book_id=:book_id and user_id=:user_id",
						{"book_id": book_id, "user_id": session['user_id'], "rate": rate, "review": review})

					book_reviews = db.execute("select * from reviews where book_id=:book_id",
											  {"book_id": book_id}).fetchall()
					review_count_bv = db.execute("select * from reviews where book_id=:book_id",
												 {"book_id": book_id}).rowcount
					res = 0
					for book_review in book_reviews:
						res += book_review.rate
					average_score_bv = res / review_count_bv
					db.execute(
						"update books set average_score_bv=:average_score_bv, review_count_bv=:review_count_bv where id=:book_id",
						{"average_score_bv": average_score_bv, "review_count_bv": review_count_bv,
						 "book_id": book_id})

			else:
				if (user_review == None):
					db.execute(
						"insert into reviews (book_id, user_id, rate) values (:book_id, :user_id, :rate)",
						{"book_id": book_id, "user_id": session['user_id'], "rate": rate})
					book = db.execute("select * from books where id=:book_id", {"book_id": book_id}).fetchone()
					average_score_bv = float(book['average_score_bv'])
					review_count_bv = int(book['review_count_bv'])

					average_score_bv = (review_count_bv * average_score_bv + rate) / (review_count_bv + 1)
					db.execute(
						"update books set average_score_bv=:average_score_bv, review_count_bv=:review_count_bv where id=:book_id",
						{"average_score_bv": average_score_bv, "review_count_bv": review_count_bv + 1,
						 "book_id": book_id})
				else:
					# book = db.execute("select * from books where id=:book_id", {"book_id": book_id}).fetchone()
					# average_score_bv = float(book['average_score_bv'])
					# review_count_bv = int(book['review_count_bv'])
					#
					# if (review_count_bv == 1):
					# 	average_score_bv = 0
					# else:
					# 	average_score_bv = average_score_bv * review_count_bv - int(user_review.rate) / (
					# 				review_count_bv - 1)
					# review_count_bv -= 1
					# average_score_bv = (review_count_bv * average_score_bv + rate) / (review_count_bv + 1)
					# db.execute(
					# 	"update books set average_score_bv=:average_score_bv, review_count_bv=:review_count_bv where id=:book_id",
					# 	{"average_score_bv": average_score_bv, "review_count_bv": review_count_bv + 1,
					# 	 "book_id": book_id})

					db.execute(
						"update reviews set rate=:rate where book_id=:book_id and user_id=:user_id",
						{"book_id": book_id, "user_id": session['user_id'], "rate": rate})

					book_reviews = db.execute("select * from reviews where book_id=:book_id",
											  {"book_id": book_id}).fetchall()
					review_count_bv = db.execute("select * from reviews where book_id=:book_id",
												 {"book_id": book_id}).rowcount
					res = 0
					for book_review in book_reviews:
						res += book_review.rate
					average_score_bv = res / review_count_bv
					db.execute(
						"update books set average_score_bv=:average_score_bv, review_count_bv=:review_count_bv where id=:book_id",
						{"average_score_bv": average_score_bv, "review_count_bv": review_count_bv,
						 "book_id": book_id})

			db.commit()

			return redirect(url_for('book', book_id=book_id))

	elif ('logged_in' in session and session['logged_in']):
		book = db.execute("select * from books where id = {id}".format(id=book_id)).fetchone()
		reviews = db.execute("select * from reviews where book_id={book_id}".format(book_id=book_id)).fetchall()
		return render_template("book.html", book=book, reviews=reviews, user_review=user_review)
	else:
		return redirect('/')


@app.route("/api/<string:isbn>", methods=['GET'])
def api(isbn):
	book = db.execute("select * from books where isbn=:isbn",
					  {"isbn": isbn}).fetchone()
	book = {
		"title": book.title,
		"author": book.author,
		"year": int(book.year),
		"isbn": book.isbn,
		"review_count": book.review_count_bv,
		"average_score": book.average_score_bv
	}

	return jsonify(book)
