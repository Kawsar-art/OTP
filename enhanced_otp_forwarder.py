import requests
import time
import re
from datetime import datetime
import phonenumbers
import pycountry
import unicodedata

# === CONFIG ===
SMS_API_URL = "http://54.206.23.26/smscdr.php"
BOT_TOKEN = "8495356297:AAFhwu7bJfCevxAqJBUtKLfCulWlwJYaq_I"
CHAT_IDS = [
    "-1002923074041",  # Original chat ID
    "-1002959636658", "-1002967717810", "-1002938549898",  # Group 1
    "-1002631105228", "-1002977099777", "-1002927795353", "-1003075823543", "-1002598456193",  # Group 2
    "-1002944916121", "-1003017167045", "-1003019851864", "-1002853296881", "-1003091924568",  # Group 3
    "-1002955519432", "-1002734689969", "-1002884784850", "-1002844264708", "-1002681210077", "-1003142966876", "-1003093573807", "-1003122294552"  # Group 4 (fixed the underscore)
]

MAX_RECORDS = 50  # Increased to fetch more records and catch more OTPs

# Global variables for robust tracking
last_msg_id = None
last_processed_timestamp = 0  # Track the last processed timestamp
total_checks = 0
total_otps = 0
start_time = None
sent_messages = set()  # Track sent messages to avoid duplicates
processed_messages = {}  # Enhanced tracking with timestamps

# ✅ New text normalization function for handling format changes
def normalize_message_text(message):
    """
    Normalize message text to handle new format requirements:
    - Remove Unicode control characters and normalize text
    - Remove multiple line breaks (\n\n)
    - Clean up formatting while preserving readable content
    """
    if not message:
        return message
    
    # Remove Unicode control characters (like \u200f, \u200e)
    message = ''.join(char for char in message if unicodedata.category(char) != 'Cf')
    
    # Normalize Unicode characters to ASCII equivalents where possible
    message = unicodedata.normalize('NFKD', message)
    
    # Remove or replace problematic Unicode characters while keeping readable text
    # Keep Arabic/other language text but remove control characters
    cleaned_chars = []
    for char in message:
        if ord(char) < 128:  # ASCII characters
            cleaned_chars.append(char)
        elif unicodedata.category(char) in ['Lu', 'Ll', 'Lt', 'Lm', 'Lo', 'Nd', 'Nl', 'No']:
            # Keep letters and numbers from other languages
            cleaned_chars.append(char)
        elif char in ' .,!?-:;()[]{}':  # Keep common punctuation
            cleaned_chars.append(char)
        else:
            # Replace other characters with space
            cleaned_chars.append(' ')
    
    message = ''.join(cleaned_chars)
    
    # Remove multiple consecutive line breaks (\n\n, \n\n\n, etc.)
    message = re.sub(r'\n{2,}', '\n', message)
    
    # Clean up multiple spaces
    message = re.sub(r' {2,}', ' ', message)
    
    # Strip leading/trailing whitespace
    message = message.strip()
    
    return message

# ✅ Enhanced OTP extractor with multiple patterns
def extract_otp(message):
    # Normalize the message first
    message = normalize_message_text(message)
    message = message.replace("–", "-").replace("—", "-")
    
    # Enhanced OTP patterns to catch more variations including bank transactions
    otp_patterns = [
        r'UGX\s+(\d{6,})',   # Bank amounts like "UGX 39693400" - could be OTP-like
        r'(?:code|otp|verification|verify|pin|password|رمز|كود|کد)[\s:]*(\d{4,8})',
        r'(?:confirm)[\s:]*(\d+)',       # "confirm: 123456"
        r'(\d{3,4}[- ]?\d{3,4})',  # Grouped digits like 123-456 or 123 456
        r'\b(\d{6,8})\b',  # Standalone 6-8 digit numbers (expanded range)
        r'\b(\d{4,5})\b'   # Standalone 4-5 digit numbers
    ]
    
    for pattern in otp_patterns:
        matches = re.findall(pattern, message, re.IGNORECASE)
        if matches:
            code = matches[0].replace("-", "").replace(" ", "")
            if 4 <= len(code) <= 8:  # Valid OTP length
                return code
    
    return "N/A"

# ✅ Country detector with enhanced error handling
def detect_country_flag(number):
    try:
        # Clean the number first
        clean_number = re.sub(r'[^\d+]', '', str(number))
        if not clean_number.startswith('+'):
            clean_number = '+' + clean_number
            
        parsed = phonenumbers.parse(clean_number, None)
        if phonenumbers.is_valid_number(parsed):
            region = phonenumbers.region_code_for_number(parsed)
            if region:
                country = pycountry.countries.get(alpha_2=region)
                if country:
                    flag = ''.join([chr(ord(c) + 127397) for c in region.upper()])
                    return country.name, flag
    except:
        pass
    return "Unknown", "🌍"

# ✅ Enhanced service detector with more services
def detect_service(msg):
    services = {
        "whatsapp": "WhatsApp",
        "telegram": "Telegram", 
        "facebook": "Facebook",
        "instagram": "Instagram",
        "gmail": "Gmail",
        "google": "Google",
        "imo": "IMO",
        "signal": "Signal",
        "twitter": "Twitter",
        "microsoft": "Microsoft",
        "yahoo": "Yahoo",
        "tiktok": "TikTok",
        "snapchat": "Snapchat",
        "linkedin": "LinkedIn",
        "uber": "Uber",
        "netflix": "Netflix",
        "amazon": "Amazon",
        "paypal": "PayPal",
        "discord": "Discord",
        "spotify": "Spotify",
        "twitch": "Twitch",
        "reddit": "Reddit",
        "pinterest": "Pinterest",
        "viber": "Viber",
        "skype": "Skype",
        "zoom": "Zoom"
    }
    msg = msg.lower()
    for key in services:
        if key in msg:
            return services[key]
    return "Unknown"

# ✅ Number mask with better formatting
def mask_number(number):
    number = str(number)
    if len(number) >= 10:
        return number[:3] + "***" + number[-4:]
    elif len(number) >= 6:
        return number[:2] + "***" + number[-2:]
    else:
        return number

# ✅ Pretty OTP formatting
def pretty_otp(otp: str) -> str:
    if len(otp) == 6:
        return f"{otp[:3]}-{otp[3:]}"
    elif len(otp) == 4:
        return f"{otp[:2]}-{otp[2:]}"
    elif len(otp) == 8:
        return f"{otp[:4]}-{otp[4:]}"
    return otp

# ✅ Enhanced message format (styled like zahid_otp.py)
def format_message(sms):
    phone_number = sms.get("phone_number", "")
    msg = sms.get("message", "").strip()
    timestamp = sms.get("timestamp", "")
    
    # Parse timestamp if available
    try:
        if timestamp and timestamp != "0":
            time_sent = datetime.fromtimestamp(float(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
        else:
            time_sent = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except:
        time_sent = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    country, flag = detect_country_flag(phone_number)
    otp_raw = extract_otp(msg)
    otp = pretty_otp(otp_raw)
    service = detect_service(msg)
    masked = mask_number(phone_number)

    # Title line like: "🔔 🇮🇷 Iran WhatsApp OTP Received..."
    title_line = f"🔔 {flag} <b>{country} {service} 𝐎𝐓𝐏 𝐑𝐞𝐜𝐞𝐢𝐯𝐞𝐝...</b>"

    return f"""<b>{title_line}</b>

🔑 <b>𝐘𝐨𝐮𝐫 𝐎𝐓𝐏:</b> <code>{otp}</code>

🕒 <b>𝚃𝚒𝚖𝚀:</b> <code>{time_sent}</code>
⚙️ <b>𝚂𝚎𝚛𝚟𝚜:</b> <code>{service}</code>
🌐 <b>𝙲𝚘𝚞𝚊𝚝𝚛𝚢:</b> <code>{country} {flag}</code>
🪪 <b>𝙽𝚞𝚖𝚋𝚎𝚛:</b> <code>{masked}</code>

💌 <b>Full-Message:</b>
<pre>{msg}</pre>

🚀 <i>𝐁𝐞 𝐀𝐜𝐭𝐢𝐯𝐞 - 𝐍𝐞𝐰 𝐎𝐓𝐏 𝐂𝐨𝐦𝐢𝐧𝐠...</i>
"""

# ✅ Send to Telegram with enhanced buttons
def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    # Create inline keyboard with single button (removed statistics button)
    inline_keyboard = {
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "🔗 Get More Services", "url": "https://t.me/work_with_trust"}]
            ]
        }
    }
    
    for chat_id in CHAT_IDS:
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        data.update(inline_keyboard)
        
        try:
            r = requests.post(url, json=data, timeout=10)
            print(f"📤 Sent to {chat_id}: {r.status_code}")
            
            # Handle rate limiting with retry
            if r.status_code == 429:
                retry_after = 30  # Default retry time
                try:
                    error_data = r.json()
                    retry_after = error_data.get('parameters', {}).get('retry_after', 30)
                except:
                    pass
                print(f"⏳ Rate limited. Retrying after {retry_after} seconds...")
                time.sleep(retry_after)
                # Retry the request
                r = requests.post(url, json=data, timeout=10)
                print(f"📤 Retry sent to {chat_id}: {r.status_code}")
            
            if r.status_code != 200:
                print(f"❌ Error response: {r.text}")
        except Exception as e:
            print(f"❌ Failed to send to {chat_id}: {e}")

# ✅ Premium startup message
def send_startup_message():
    startup_text = f"""🔧 Enhanced OTP Forwarder by <a href="https://t.me/work_with_trust">XENO</a>

🚀 Bot is working! Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
📡 Connected to External SMS API
🔄 Polling every 3 seconds for new OTPs"""

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    for chat_id in CHAT_IDS:
        data = {
            "chat_id": chat_id,
            "text": startup_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, json=data, timeout=10)
            print(f"🚀 Startup message sent to {chat_id}: {r.status_code}")
        except Exception as e:
            print(f"❌ Failed to send startup message to {chat_id}: {e}")

# ✅ Premium shutdown message  
def send_shutdown_message():
    global total_checks, total_otps, start_time
    runtime = int(time.time() - start_time) if start_time else 0
    
    shutdown_text = f"""🛑 Enhanced OTP Forwarder Stopped

📊 <b>Session Statistics:</b>
• Total API checks: {total_checks}
• Total OTPs forwarded: {total_otps}
• Runtime: {runtime} seconds
• Average checks/min: {round((total_checks * 60) / runtime, 1) if runtime > 0 else 0}

✅ Session completed successfully!"""

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    for chat_id in CHAT_IDS:
        data = {
            "chat_id": chat_id,
            "text": shutdown_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, json=data, timeout=10)
            print(f"🛑 Shutdown message sent to {chat_id}: {r.status_code}")
        except Exception as e:
            print(f"❌ Failed to send shutdown message to {chat_id}: {e}")

# ✅ Fetch SMS from external API with retry mechanism
def fetch_latest_sms():
    max_retries = 3
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            response = requests.get(SMS_API_URL, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data.get("success") == True:
                    sms_records = data.get("sms_records", [])
                    # Handle different timestamp formats
                    for record in sms_records:
                        timestamp = record.get("timestamp", "0")
                        try:
                            # Try to convert to float first (Unix timestamp)
                            float(timestamp)
                        except ValueError:
                            # If it's a date string, convert to Unix timestamp
                            try:
                                dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                                record["timestamp"] = str(int(dt.timestamp()))
                            except ValueError:
                                # If parsing fails, use current timestamp
                                record["timestamp"] = str(int(time.time()))
                    
                    # Sort by timestamp to ensure chronological processing
                    sms_records.sort(key=lambda x: float(x.get("timestamp", 0)))
                    return sms_records[-MAX_RECORDS:]  # Return latest records
            else:
                print(f"⚠️ API returned status {response.status_code}, attempt {attempt + 1}")
        except Exception as e:
            print(f"❌ API Error (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
    
    print("❌ All API retry attempts failed")
    return []

# ✅ Check if message contains OTP keywords
def is_otp_message(message):
    # Enhanced OTP keywords including bank and financial terms
    otp_keywords = [
        "otp", "code", "verify", "verification", "pin", "password", "confirm", "confirmation",
        "كود", "رمز", "تأكيد", "کد", "تایید", "رمز عبور",
        "bank", "transaction", "stanbic", "ugx", "account", "balance", "transfer",
        "whatsapp", "telegram", "facebook", "instagram", "google", "apple", "uber"
    ]
    message_lower = message.lower()
    
    # Check for OTP keywords
    if any(keyword in message_lower for keyword in otp_keywords):
        return True
    
    # Check for numeric patterns that could be OTPs
    if re.search(r'\b\d{4,8}\b', message):
        return True
        
    return False

# ✅ Enhanced main loop with robust OTP detection
def main():
    global last_msg_id, total_checks, total_otps, start_time, sent_messages, last_processed_timestamp, processed_messages
    
    # Initialize start time
    start_time = time.time()
    
    # Send startup message
    send_startup_message()
    print("🚀 ENHANCED OTP BOT LIVE...")
    print(f"📡 Monitoring: {SMS_API_URL}")
    print(f"🎯 Target chats: {len(CHAT_IDS)}")
    print("🔧 Robust Mode: Timestamp tracking + Retry mechanism")
    print("=" * 50)
    
    try:
        while True:
            total_checks += 1
            
            sms_list = fetch_latest_sms()
            if sms_list:
                new_messages_found = 0
                
                for sms in sms_list:
                    timestamp = float(sms.get("timestamp", 0))
                    phone_number = sms.get("phone_number", "")
                    message_text = sms.get("message", "")
                    
                    # Create multiple unique identifiers for robust duplicate detection
                    msg_id = f"{phone_number}_{timestamp}_{hash(message_text)}"
                    timestamp_id = f"{timestamp}_{phone_number}"
                    
                    # Only process messages newer than our last processed timestamp
                    if timestamp > last_processed_timestamp:
                        # Check if this is a new OTP message we haven't sent
                        # Removed strict OTP extraction requirement - process ALL detected messages
                        if (msg_id not in sent_messages and 
                            timestamp_id not in processed_messages and
                            is_otp_message(message_text)):
                            
                            # Try to extract OTP, but send message even if extraction fails
                            otp_code = extract_otp(message_text)
                            if otp_code == "N/A":
                                # For messages without clear OTP, try to find any number
                                number_match = re.search(r'\b\d{4,}\b', message_text)
                                if number_match:
                                    otp_code = number_match.group()
                                else:
                                    otp_code = "Unknown"
                            
                            formatted = format_message(sms)
                            send_telegram(formatted)
                            
                            # Track the message in multiple ways
                            sent_messages.add(msg_id)
                            processed_messages[timestamp_id] = time.time()
                            total_otps += 1
                            new_messages_found += 1
                            
                            # Extract OTP for logging (use the already extracted/found code)
                            service = detect_service(message_text)
                            print(f"✅ OTP Forwarded: {service} - {otp_code} (TS: {timestamp})")
                            
                            # Update last processed timestamp
                            last_processed_timestamp = max(last_processed_timestamp, timestamp)
                
                # Clean up old tracking data periodically
                if len(sent_messages) > 2000:
                    sent_messages = set(list(sent_messages)[-1000:])
                
                if len(processed_messages) > 1000:
                    # Remove entries older than 1 hour
                    current_time = time.time()
                    processed_messages = {k: v for k, v in processed_messages.items() 
                                        if current_time - v < 3600}
                
                if new_messages_found > 0:
                    print(f"📨 Processed {new_messages_found} new OTP(s) in this batch")
            
            # Status update every 100 checks
            if total_checks % 100 == 0:
                runtime = int(time.time() - start_time)
                print(f"📊 Status: {total_checks} checks, {total_otps} OTPs, {runtime}s runtime")
                print(f"🕒 Last processed timestamp: {last_processed_timestamp}")
            
            time.sleep(2)  # Reduced from 3 to 2 seconds for faster polling
            
    except KeyboardInterrupt:
        print("\n🛑 Shutdown initiated...")
        send_shutdown_message()
        print("✅ Shutdown complete!")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        send_shutdown_message()

if __name__ == "__main__":
    # Configuration is already set with actual values
    # BOT_TOKEN and CHAT_IDS are configured
    
    main()