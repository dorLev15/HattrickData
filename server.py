from fastapi import FastAPI, Request, Query
from pydantic import BaseModel
from typing import Optional
import sqlite3
from datetime import datetime
import json
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace "*" with your frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ✅ Initialize DB
def init_db():
    conn = sqlite3.connect("players.db")
    cursor = conn.cursor()

    # Static player info
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id TEXT PRIMARY KEY,
            name TEXT,
            specialties TEXT
        )
    ''')

    # Weekly stats
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_stats (
            player_id TEXT,
            TSI TEXT,
            salary TEXT,
            fitness TEXT,
            form TEXT,
            skills TEXT,
            date TEXT,
            age TEXT,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')

    conn.commit()
    conn.close()


# ✅ Ensure age column exists in player_stats
def add_age_to_stats_if_missing():
    conn = sqlite3.connect("players.db")
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(player_stats)")
    columns = [col[1] for col in cursor.fetchall()]
    if "age" not in columns:
        cursor.execute("ALTER TABLE player_stats ADD COLUMN age TEXT")
        conn.commit()
    conn.close()


init_db()
add_age_to_stats_if_missing()


# ✅ Pydantic model for incoming player data
class Player(BaseModel):
    name: str
    age: str
    TSI: str
    salary: str
    specialties: str
    form: str
    fitness: str
    skills: dict
    date: Optional[str]


# ✅ Save new player data
@app.post("/players/{player_id}")
async def save_player(player_id: str, request: Request):
    conn = None
    try:
        player_data = await request.json()
        print(f"📥 Received raw body for player {player_id}:", player_data)

        # Convert skills string to dict if needed
        if isinstance(player_data.get("skills"), str):
            try:
                player_data["skills"] = json.loads(player_data["skills"])
            except json.JSONDecodeError as e:
                return {"error": f"Invalid JSON in skills: {e}"}

        player = Player(**player_data)

        # Convert date from "DD/MM/YYYY" to "YYYY-MM-DD" for sorting
        try:
            iso_date = datetime.strptime(player.date, "%d/%m/%Y").strftime("%Y-%m-%d")
        except:
            iso_date = datetime.now().strftime("%Y-%m-%d")

        conn = sqlite3.connect("players.db")
        cursor = conn.cursor()

        # Insert or update base player info (without age)
        cursor.execute('''
            INSERT INTO players (id, name, specialties)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                specialties = excluded.specialties
        ''', (
            player_id,
            player.name,
            player.specialties,
        ))

        # Insert weekly stats including age
        cursor.execute('''
            INSERT INTO player_stats (player_id, TSI, salary, fitness, form, skills, date, age)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            player_id,
            player.TSI,
            player.salary,
            player.fitness,
            player.form,
            json.dumps(player.skills),
            iso_date,
            player.age
        ))

        conn.commit()
        return {"message": f"✅ Player {player.name} saved successfully"}

    except Exception as e:
        print("❌ Error occurred:", e)
        return {"error": str(e)}
    finally:
        if conn:
            conn.close()


# ✅ Get all player stats (joined with player info)
@app.get("/players")
def get_all_players(player_id: Optional[str] = Query(None), date: Optional[str] = Query(None)):
    conn = sqlite3.connect("players.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = '''
        SELECT p.id, p.name, p.specialties, 
               s.age, s.TSI, s.salary, s.fitness, s.form, s.skills, s.date
        FROM player_stats s
        JOIN players p ON p.id = s.player_id
    '''
    filters = []
    values = []

    if player_id:
        filters.append("p.id = ?")
        values.append(player_id)

    if date:
        try:
            iso_date = datetime.strptime(date, "%d/%m/%Y").strftime("%Y-%m-%d")
            filters.append("s.date = ?")
            values.append(iso_date)
        except:
            return {"error": "Invalid date format. Use DD/MM/YYYY."}

    if filters:
        query += " WHERE " + " AND ".join(filters)

    query += " ORDER BY s.date DESC"

    cursor.execute(query, values)
    rows = cursor.fetchall()

    result = []
    for row in rows:
        row_dict = dict(row)
        try:
            row_dict["date"] = datetime.strptime(row_dict["date"], "%Y-%m-%d").strftime("%d/%m/%Y")
        except:
            pass
        row_dict["skills"] = json.loads(row_dict["skills"])
        result.append(row_dict)

    conn.close()
    return result
