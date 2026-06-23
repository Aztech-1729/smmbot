# VPS Deployment Guide for SMM Bot (Non-Docker)

Since Docker has been entirely removed from the project, you must run the bot as a native Python background process on your VPS. This guide assumes you are using an **Ubuntu 20.04 or 22.04 VPS**.

## Step 1: Install System Dependencies
Connect to your VPS via SSH and install Python 3.12, Redis, and MongoDB natively.

```bash
# Update package list
sudo apt update && sudo apt upgrade -y

# Install Python 3.12 (if not already installed)
sudo apt install software-properties-common -y
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev -y

# Install Redis
sudo apt install redis-server -y

# Install MongoDB (Default instructions for Ubuntu)
sudo apt install mongodb -y
# If mongodb is not in the default apt repo, see official MongoDB installation docs.
```

## Step 2: Configure Redis on Port 6380
By default, Redis runs on `6379`. Your bot requires `6380`.
You need to change the Redis configuration to run on the correct port.

```bash
sudo nano /etc/redis/redis.conf
```
Find the line that says `port 6379` and change it to `port 6380`. Save and exit.

Restart Redis to apply changes:
```bash
sudo systemctl restart redis-server
sudo systemctl enable redis-server
```

## Step 3: Clone Your Repository
Download your code from GitHub onto the VPS.

```bash
git clone https://github.com/Aztech-1729/smmbot.git
cd smmbot
```

## Step 4: Setup Python Virtual Environment
We highly recommend using a virtual environment.

```bash
# Create the virtual environment
python3.12 -m venv venv

# Activate it
source venv/bin/activate

# Install the required packages
pip install -r requirements.txt
```

## Step 5: Configure Environment Variables
You must create the `.env` file on the VPS.

```bash
nano .env
```
Paste your production settings:
```env
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
MONGO_URL=mongodb://localhost:27017/smmbot
REDIS_URL=redis://localhost:6380/0
API_ID=37328890
API_HASH=970f55bcf3fe0fcda7cd16bb64213ce5
```

## Step 6: Setup Systemd Service (Process Manager)
To keep the bot running 24/7 (even if it crashes or the server reboots), we will create a `systemd` background service.

Create the service file:
```bash
sudo nano /etc/systemd/system/smmbot.service
```

Paste the following configuration (replace `root` with your actual Linux username if you're not using root, and update the `/path/to/smmbot` with the actual path to where you cloned the repo):
```ini
[Unit]
Description=SMM Telegram Bot
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/root/smmbot
Environment="PATH=/root/smmbot/venv/bin"
ExecStart=/root/smmbot/venv/bin/python -m bot.main
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

## Step 7: Start and Enable the Bot
Now start the bot and enable it to automatically start when the VPS boots up.

```bash
# Reload systemd manager configuration
sudo systemctl daemon-reload

# Start the bot
sudo systemctl start smmbot

# Enable the bot to run on server boot
sudo systemctl enable smmbot
```

## How to View Logs
If you need to check if the bot is running properly or view errors:
```bash
sudo journalctl -u smmbot -f
```
