import os
import datetime
import subprocess
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import zipfile
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def backup_mongodb():
    # Create backup directory if it doesn't exist
    backup_dir = "mongodb_backups"
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    # Generate backup filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"mongodb_backup_{timestamp}"
    backup_path = os.path.join(backup_dir, backup_name)

    # MongoDB connection details from environment variables
    mongo_uri = os.getenv('MONGODB_URI')
    mongo_db = os.getenv('MONGODB_NAME')

    # Create backup using mongodump
    try:
        subprocess.run([
            'mongodump',
            '--uri', mongo_uri,
            '--db', mongo_db,
            '--out', backup_path
        ], check=True)
        print(f"Backup created successfully at {backup_path}")
        return backup_path
    except subprocess.CalledProcessError as e:
        print(f"Error creating backup: {e}")
        return None

def zip_backup(backup_path):
    if not backup_path:
        return None
    
    zip_path = f"{backup_path}.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(backup_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, backup_path)
                zipf.write(file_path, arcname)
    
    return zip_path

def send_email(attachment_path):
    # Email configuration from environment variables
    smtp_server = os.getenv('SMTP_SERVER')
    smtp_port = int(os.getenv('SMTP_PORT', 587))
    sender_email = os.getenv('EMAIL_USER')
    sender_password = os.getenv('EMAIL_PASSWORD')
    recipient_email = os.getenv('RECIPIENT_EMAIL')

    if not all([smtp_server, sender_email, sender_password, recipient_email]):
        print("Missing email configuration in environment variables")
        return

    # Create message
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = f"MongoDB Backup - {datetime.datetime.now().strftime('%Y-%m-%d')}"

    # Add body
    body = f"MongoDB backup for {datetime.datetime.now().strftime('%Y-%m-%d')}"
    msg.attach(MIMEText(body, 'plain'))

    # Add attachment
    with open(attachment_path, 'rb') as f:
        part = MIMEApplication(f.read(), Name=os.path.basename(attachment_path))
    part['Content-Disposition'] = f'attachment; filename="{os.path.basename(attachment_path)}"'
    msg.attach(part)

    # Send email
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        print("Email sent successfully")
    except Exception as e:
        print(f"Error sending email: {e}")

def cleanup_old_backups(backup_dir, days_to_keep=30):
    now = datetime.datetime.now()
    for filename in os.listdir(backup_dir):
        file_path = os.path.join(backup_dir, filename)
        if os.path.isfile(file_path):
            file_time = datetime.datetime.fromtimestamp(os.path.getctime(file_path))
            if (now - file_time).days > days_to_keep:
                os.remove(file_path)
                print(f"Removed old backup: {file_path}")

def main():
    # Create backup
    backup_path = backup_mongodb()
    if not backup_path:
        return

    # Zip backup
    zip_path = zip_backup(backup_path)
    if not zip_path:
        return

    # Send email with backup
    send_email(zip_path)

    # Cleanup old backups
    cleanup_old_backups("mongodb_backups")

if __name__ == "__main__":
    main() 