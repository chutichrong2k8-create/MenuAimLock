import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import json
import random
import string
import io
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import uuid
import hashlib
import time
request_log = {}

def rate_limit(ip, limit=10, window=10):
    now = time.time()

    if ip not in request_log:
        request_log[ip] = []

    request_log[ip] = [t for t in request_log[ip] if now - t < window]

    if len(request_log[ip]) >= limit:
        return False

    request_log[ip].append(now)
    return True

with open("config.json", "r") as f:
    config = json.load(f)

TOKEN = config["token"]
ALLOWED_ROLE = config["allowed_role"]
LOG_CHANNEL_ID = config["log_channel_id"]

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


def load_db():
    with open("database.json", "r") as f:
        return json.load(f)


def save_db(data):
    with open("database.json", "w") as f:
        json.dump(data, f, indent=4)


app = Flask(__name__)
CORS(app)

@app.route("/api/check")
def api_check():

    key = request.args.get("key")
    hwid = request.args.get("hwid")

    if not hwid:
        return jsonify({"status": "no_hwid"})

    ip = request.remote_addr

    if not rate_limit(ip):
        return jsonify({"status": "rate_limited"})

    if not key:
        return jsonify({"status": "no_key"})

    db = load_db()

    for k in db["keys"]:

        if k["key"] == key:

            expire_time = datetime.strptime(k["expire_at"], "%Y-%m-%d %H:%M:%S")

            if expire_time < datetime.now():
                return jsonify({"status": "expired"})

            if "hwid" not in k:
                k["hwid"] = None

if k["key"] == key:

    expire_time = datetime.strptime(k["expire_at"], "%Y-%m-%d %H:%M:%S")

    if expire_time < datetime.now():
        return jsonify({"status": "expired"})

    if "hwids" not in k:
        k["hwids"] = []

    max_devices = k.get("devices", 1)

    if hwid in k["hwids"]:
        pass
    elif len(k["hwids"]) < max_devices:
        k["hwids"].append(hwid)
    else:
        return jsonify({"status": "device_limit"})

    expire_time = datetime.strptime(k["expire_at"], "%Y-%m-%d %H:%M:%S")

    if expire_time < datetime.now():
        return jsonify({"status": "expired"})

    if "hwids" not in k:
        k["hwids"] = []

    max_devices = k.get("devices", 1)

    if hwid in k["hwids"]:
        pass

    elif len(k["hwids"]) < max_devices:
        k["hwids"].append(hwid)

    else:
        return jsonify({"status": "device_limit"})

    k["last_ip"] = ip
    k["last_login"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    save_db(db)

    return jsonify({"status": "valid"})

    return jsonify({"status": "invalid_key"})

def generate_key(prefix="KEY", length=8):
    characters = string.ascii_uppercase + string.digits
    random_part = ''.join(random.choice(characters) for _ in range(length))
    formatted = f"{random_part[:4]}-{random_part[4:]}"
    return f"{prefix.upper()}-{formatted}"



class DownloadView(discord.ui.View):
    def __init__(self, keys):
        super().__init__(timeout=120)
        self.keys = keys

    @discord.ui.button(label="📥 Download TXT", style=discord.ButtonStyle.green)
    async def download(self, interaction: discord.Interaction, button: discord.ui.Button):

        file_content = "\n".join(self.keys)
        file_bytes = io.BytesIO(file_content.encode("utf-8"))
        file = discord.File(file_bytes, filename="keys.txt")

        await interaction.response.send_message(
            "📂 File key của bạn:",
            file=file,
            ephemeral=True
        )

    @discord.ui.button(label="📋 Copy All Keys", style=discord.ButtonStyle.primary)
    async def copy(self, interaction: discord.Interaction, button: discord.ui.Button):

        key_text = "\n".join(self.keys)

        await interaction.response.send_message(
            f"🔑 Copy key:\n```{key_text}```",
            ephemeral=True
        )



@bot.event
async def on_ready():
    await tree.sync()
    print(f"Bot online: {bot.user}")


@tree.command(name="buildkey", description="Tạo nhiều key")
@app_commands.describe(
    count="Số lượng key",
    days="Số ngày hiệu lực",
    prefix="Prefix của key"
)
async def buildkey(interaction: discord.Interaction, count: int, days: int, prefix: str):

    db = load_db()
    created_keys = []

    for _ in range(count):
        key = generate_key(prefix)
        expire_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

        db["keys"].append({
            "key": key,
            "prefix": prefix,
            "hwid": None,
            "created_by": interaction.user.name,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "expire_at": expire_date,
            "days": days
        })

        created_keys.append(key)

    save_db(db)

    key_list = "\n".join(created_keys)

    embed = discord.Embed(
        title="📦 Đã Tạo Key Thành Công",
        description=f"Tổng cộng **{count}** key đã được tạo",
        color=0x5865F2
    )

    embed.add_field(
        name="🔑 Danh Sách Key",
        value=f"```{key_list}```",
        inline=False
    )

    embed.add_field(name="📦 Prefix", value=prefix, inline=True)
    embed.add_field(name="⏰ Hiệu lực", value=f"{days} ngày", inline=True)
    embed.add_field(name="👤 Người tạo", value=interaction.user.name, inline=True)

    view = DownloadView(created_keys)

    await interaction.response.send_message(embed=embed, view=view)

    log_channel = bot.get_channel(LOG_CHANNEL_ID)

    if log_channel:
        await log_channel.send(
            f"{interaction.user.mention} đã tạo {count} key | Prefix: {prefix.upper()}"
        )



@tree.command(name="createkey", description="Tạo 1 key")
@app_commands.describe(
    days="Số ngày hiệu lực",
    prefix="Prefix",
    devices="Số thiết bị"
)
async def createkey(interaction: discord.Interaction, days: int, prefix: str, devices: int):

  
    db = load_db()

    key = generate_key(prefix)
    expire_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    db["keys"].append({
        "key": key,
        "prefix": prefix,
        "devices": devices,
        "hwid": None,
        "created_by": interaction.user.name,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "expire_at": expire_date,
        "days": days
    })

    save_db(db)

    embed = discord.Embed(
        title="🔑 Key Đã Được Tạo",
        color=0x5865F2
    )

    embed.add_field(name="Key", value=f"```{key}```", inline=False)
    embed.add_field(name="⏰ Hiệu lực", value=f"{days} ngày", inline=True)
    embed.add_field(name="📱 Thiết bị", value=str(devices), inline=True)

    view = DownloadView([key])

    await interaction.response.send_message(embed=embed, view=view)



@tree.command(name="check", description="Xem chi tiết key")
async def check(interaction: discord.Interaction, key: str):

    db = load_db()

    for k in db["keys"]:
        if k["key"] == key:

            hwid = k.get("hwid", "Chưa gắn")
            devices = k.get("devices", 1)
            created_by = k.get("created_by", "Unknown")
            created_at = k.get("created_at", "Unknown")
            expire = k.get("expire_at", "Unknown")
            last_login = k.get("last_login", "Chưa login")
            ip = k.get("last_ip", "Unknown")

            expire_time = datetime.strptime(k["expire_at"], "%Y-%m-%d %H:%M:%S")

            if expire_time < datetime.now():
                status = "⛔ Hết hạn"
            else:
                status = "🟢 Hoạt động"

            embed = discord.Embed(
                title=f"🔎 Chi Tiết Key: {key}",
                description=f"Thông tin tổng quan về Key `{key}`",
                color=0x2ecc71
            )

            embed.add_field(name="🔑 Key", value=f"`{key}`", inline=False)
            embed.add_field(name="💻 HWID Đã Gán", value=f"{hwid}", inline=False)

            embed.add_field(name="🟢 Trạng Thái", value=status, inline=True)
            embed.add_field(name="📊 Thiết Bị", value=f"{devices}", inline=True)
            embed.add_field(name="⏰ Hạn Dùng", value=expire, inline=True)

            embed.add_field(name="🌐 IP Cuối", value=f"`{ip}`", inline=True)
            embed.add_field(name="🕒 Lần Đăng Nhập Cuối", value=last_login, inline=True)

            embed.add_field(name="👤 Người Tạo Key", value=f"`{created_by}`", inline=True)
            embed.add_field(name="📅 Ngày Tạo Key", value=created_at, inline=True)

            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

    await interaction.response.send_message("❌ Key không tồn tại", ephemeral=True)


@tree.command(name="delete", description="Xoá key")
async def delete(interaction: discord.Interaction, key: str):

    db = load_db()

    db["keys"] = [k for k in db["keys"] if k["key"] != key]

    save_db(db)

    await interaction.response.send_message("🗑 Đã xoá key", ephemeral=True)

@tree.command(name="deleteexpired", description="Xoá tất cả key đã hết hạn")
async def deleteexpired(interaction: discord.Interaction):

    db = load_db()

    now = datetime.now()
    remaining = []
    removed = 0

    for k in db["keys"]:
        expire_time = datetime.strptime(k["expire_at"], "%Y-%m-%d %H:%M:%S")

        if expire_time < now:
            removed += 1
        else:
            remaining.append(k)

    db["keys"] = remaining
    save_db(db)

    await interaction.response.send_message(
        f"🗑 Đã xoá {removed} key hết hạn",
        ephemeral=True
    )
@tree.command(name="deleteall", description="Xoá toàn bộ key")
async def deleteall(interaction: discord.Interaction):

    db = load_db()

    total = len(db["keys"])

    db["keys"] = []

    save_db(db)

    await interaction.response.send_message(
        f"💥 Đã xoá toàn bộ {total} key trong database",
        ephemeral=True
    )

@tree.command(name="stats", description="Thống kê số lượng key")
async def stats(interaction: discord.Interaction):

    db = load_db()

    total = len(db["keys"])

    now = datetime.now()
    active = 0
    expired = 0

    for k in db["keys"]:
        expire_time = datetime.strptime(k["expire_at"], "%Y-%m-%d %H:%M:%S")
        if expire_time > now:
            active += 1
        else:
            expired += 1

    embed = discord.Embed(title="📊 Thống Kê Key", color=0x5865F2)

    embed.add_field(name="🔑 Tổng Key", value=str(total), inline=False)
    embed.add_field(name="✅ Key còn hạn", value=str(active), inline=True)
    embed.add_field(name="⛔ Key hết hạn", value=str(expired), inline=True)

    await interaction.response.send_message(embed=embed)

@tree.command(name="resethwid", description="Reset HWID của key")
async def resethwid(interaction: discord.Interaction, key: str):

    db = load_db()

    for k in db["keys"]:
        if k["key"] == key:

            k["hwid"] = None
            save_db(db)

            return await interaction.response.send_message(
                "♻️ Đã reset HWID của key",
                ephemeral=True
            )

    await interaction.response.send_message(
        "❌ Key không tồn tại",
        ephemeral=True
    )

@tree.command(name="resetkeys", description="Reset toàn bộ database key")
async def resetkeys(interaction: discord.Interaction):

    db = load_db()

    total = len(db["keys"])

    db["keys"] = []

    save_db(db)

    await interaction.response.send_message(
        f"♻️ Đã reset database. Xoá {total} key.",
        ephemeral=True
    )


import time
import threading

def run_api():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

threading.Thread(target=run_api).start()

while True:
    try:
        bot.run(TOKEN, reconnect=True)
    except Exception as e:
        print("Bot crash:", e)
        print("Restart sau 5s...")
        time.sleep(5)