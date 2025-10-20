# 🛡️ Discord NSFW Image Moderator (ONNX + nsfw-detector)

A complete step-by-step setup guide for building an **NSFW image moderation Discord bot** using  
`ONNXRuntime`, `nsfw-detector`, and the **Hugging Face ONNX NSFW Model**.

Built for **Ubuntu**, **Termux (via proot-distro)**, or **any Linux-based server**.

---

## 📖 Table of Contents

1. [Overview](#-overview)
2. [Ubuntu / Termux Setup](#-ubuntu--termux-setup)
3. [Environment Setup](#-environment-setup)
4. [Install Dependencies](#-install-dependencies)
5. [Download ONNX Model](#-download-onnx-model)
6. [Create Required Files](#-create-required-files)
7. [Run the Bot](#-run-the-bot)
8. [Adjust Threshold](#-adjust-threshold)
9. [Troubleshooting](#-troubleshooting)
10. [Credits & License](#-credits--license)

---

## 🧭 Overview

discord-nsfw-detector/ ├── bot.py ├── run_onnx.py ├── nsfw_model.onnx ├── requirements.txt └── README.md

This bot uses **ONNXRuntime** for fast inference and the **Hugging Face NSFW model** to detect explicit images.  
It automatically deletes NSFW content and warns users on Discord.

---

## 🐧 Ubuntu / Termux Setup

### 🔹 For Termux
```bash
pkg update -y && pkg upgrade -y
pkg install proot-distro -y
proot-distro install ubuntu
proot-distro login ubuntu




🔹 For Ubuntu (VPS or Local)

sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv git wget -y




🧱 Environment Setup

# Clone your project
git clone https://github.com/Ayan-cyber134/opennsfw2.git
cd opennsfw2

# Create and activate virtual environment
python3 -m venv nsfw-env
source nsfw-env/bin/activate




📦 Install Dependencies

Create a requirements.txt file:

nano requirements.txt

Paste:

discord.py==2.6.4
aiofiles
requests
onnxruntime
pillow
nsfw-detector
numpy

Then install all:

pip install -r requirements.txt




🤖 Download ONNX Model

wget https://huggingface.co/onnx-community/nsfw-image-detector-ONNX/resolve/main/onnx/model.onnx -O nsfw_model.onnx

Verify:

ls
# Should show: nsfw_model.onnx





▶️ Run the Bot

source nsfw-env/bin/activate
python3 bot.py



🎚️ Adjust Threshold

Mode	Threshold	Behavior

🔒 Strict	0.30	Catches even borderline NSFW
⚖️ Balanced	0.35	Recommended for public servers
🪶 Lenient	0.45	Allows minor skin exposure
Recommended is 0.5 (default)




🔄 Auto-Run on Startup

Add to startup.sh

#!/bin/bash
cd ~/opennsfw2
source nsfw-env/bin/activate
python3 bot.py

Make executable:

chmod +x startup.sh

Run:

./startup.sh




🩻 Troubleshooting

Issue	Cause	Fix

Got invalid dimensions for input	Wrong input shape	Use (1,3,224,224) as in script
pthread_setaffinity_np failed	ONNX threading	Harmless warning
ModuleNotFoundError: tensorflow	TensorFlow not needed	pip uninstall tensorflow -y
discord.gateway ratelimited	API cooldown	Wait 60s
ONNXRuntimeError: INVALID_ARGUMENT	Wrong resize/transpose	Use provided run_onnx.py





🧹 Clean Up & Optimization

pip uninstall tensorflow tensorboard tensorflow-hub -y
pip cache purge

To check installed packages:

pip list




🔁 Update Everything

pip install --upgrade pip onnxruntime pillow nsfw-detector discord.py




🌐 Model Source

Model: Hugging Face – ONNX NSFW Image Detector
Input: (1, 3, 224, 224)
Output: Float value — higher means more NSFW probability
probability



💡 Credits & License

Developed using:

discord.py

onnxruntime

nsfw-detector

Hugging Face ONNX Models




⭐ Star this repo if it helped you build your own NSFW moderator bot!
