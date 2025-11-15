from flask import Flask
import threading
import logging
import sys
import asyncio
import re
import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import imaplib
import email
from email.header import decode_header
from dataclasses import dataclass
from typing import Optional, Tuple
import random
from PIL import Image
import io

# Create Flask app for health checks
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 CC Spending Bot is Running!"

@app.route('/health')
def health():
    return "✅ Bot is healthy and running!"

@app.route('/ping')
def ping():
    return "pong"

def run_flask():
    """Run Flask app in background"""
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# Start Flask in background thread
flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

@dataclass
class CardInfo:
    cardholder_name: str = ""
    card_number: str = ""
    card_type: str = ""
    expiry: str = ""
    cvc: str = ""
    billing_address: str = ""
    time: str = ""

@dataclass
class OTPInfo:
    card_number: str = ""
    otp: str = ""
    time: str = ""

class CoinGateAutomation:
    def __init__(self, telegram_bot=None, chat_id=None):
        self.driver = None
        self.current_card = None
        self.otp_info = None
        self.transaction_count = 0
        self.running = False
        self.telegram_bot = telegram_bot
        self.chat_id = chat_id
        self.setup_driver()
        
    def setup_driver(self):
        """Setup Chrome driver for cloud environment"""
        chrome_options = Options()
        
        # Cloud-optimized settings
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            # For cloud environment
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            logging.info("✅ Chrome driver initialized successfully")
        except Exception as e:
            logging.error(f"❌ Chrome setup failed: {e}")
            # Fallback to ChromeDriver manager
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                logging.info("✅ Chrome driver initialized with webdriver_manager")
            except Exception as e2:
                logging.error(f"❌ All Chrome setups failed: {e2}")
                raise

    async def send_screenshot(self, caption: str):
        """Take screenshot and send to Telegram"""
        try:
            if not self.telegram_bot or not self.chat_id:
                return
                
            # Take screenshot
            screenshot = self.driver.get_screenshot_as_png()
            
            # Send to Telegram
            await self.telegram_bot.send_photo(
                chat_id=self.chat_id,
                photo=screenshot,
                caption=caption
            )
            logging.info(f"📸 Screenshot sent: {caption}")
        except Exception as e:
            logging.error(f"❌ Failed to send screenshot: {e}")

    async def send_message(self, message: str):
        """Send text message to Telegram"""
        try:
            if not self.telegram_bot or not self.chat_id:
                return
                
            await self.telegram_bot.send_message(
                chat_id=self.chat_id,
                text=message
            )
            logging.info(f"📨 Message sent: {message}")
        except Exception as e:
            logging.error(f"❌ Failed to send message: {e}")

    async def debug_check_driver(self):
        """Debug method to check driver status"""
        try:
            if self.driver:
                current_url = self.driver.current_url
                page_title = self.driver.title
                await self.send_message(f"🔧 Driver Status: ACTIVE\nURL: {current_url}\nTitle: {page_title}")
                return True
            else:
                await self.send_message("❌ Driver Status: NOT INITIALIZED")
                return False
        except Exception as e:
            await self.send_message(f"❌ Driver Error: {e}")
            return False

    def extract_card_info(self, message: str) -> Optional[CardInfo]:
        """Extract card information from Telegram message with improved parsing"""
        try:
            card_info = CardInfo()
            
            # More flexible patterns
            patterns = {
                'cardholder_name': r"👤 Cardholder Name:\s*(.+)",
                'card_number': r"💳 Card Number:\s*(\d+)",
                'card_type': r"🏦 Card Type:\s*(.+)",
                'expiry': r"📅 Expiry:\s*(\d{1,2}/\d{2,4})",
                'cvc': r"🔐 CVC:\s*(\d{3,4})",
                'billing_address': r"🏠 Billing Address:\s*(.+)",
                'time': r"⏰ Time:\s*(.+)"
            }
            
            for field, pattern in patterns.items():
                match = re.search(pattern, message, re.IGNORECASE | re.MULTILINE)
                if match:
                    setattr(card_info, field, match.group(1).strip())
            
            # Validate required fields
            if card_info.card_number and len(card_info.card_number) >= 15 and card_info.cvc:
                logging.info(f"✅ Card parsed successfully: {card_info.card_number[-4:]}")
                return card_info
            else:
                logging.error(f"❌ Invalid card data - Number: {card_info.card_number}, CVC: {card_info.cvc}")
                return None
        except Exception as e:
            logging.error(f"❌ Error extracting card info: {e}")
            return None
    
    def extract_otp_info(self, message: str) -> Optional[OTPInfo]:
        """Extract OTP information from Telegram message"""
        try:
            otp_info = OTPInfo()
            
            card_match = re.search(r"💳 Card Number:\s*(\d+)", message)
            otp_match = re.search(r"🔢 OTP:\s*(\d+)", message)
            time_match = re.search(r"⏰ Time:\s*(.+)", message)
            
            if card_match and otp_match:
                otp_info.card_number = card_match.group(1).strip()
                otp_info.otp = otp_match.group(1).strip()
                otp_info.time = time_match.group(1).strip() if time_match else ""
                logging.info(f"✅ OTP parsed for card: {otp_info.card_number[-4:]}")
                return otp_info
            return None
        except Exception as e:
            logging.error(f"❌ Error extracting OTP info: {e}")
            return None
    
    async def navigate_to_giftcard_page(self):
        """Navigate to the CoinGate gift card page"""
        try:
            await self.send_message("🎯 Navigating to CoinGate Gift Card page...")
            self.driver.get("https://coingate.com/gift-cards/razer-gold-rixty")
            
            # Wait for page to load completely
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            logging.info("✅ Successfully navigated to gift card page")
            await self.send_screenshot("🎯 Landed on CoinGate Gift Card Page")
            return True
        except Exception as e:
            logging.error(f"❌ Failed to navigate to gift card page: {e}")
            await self.send_message(f"❌ Navigation failed: {e}")
            return False
    
    async def select_region_and_value(self, card_type: str):
        """Select region and value based on card type"""
        try:
            await self.send_message("⚙️ Selecting region and value...")
            
            # Determine value based on card type and transaction count
            if card_type.lower() == "mastercard" and self.transaction_count == 0:
                target_value = "500"
            else:
                target_value = "100"
            
            logging.info(f"💲 Selecting ${target_value} USD for {card_type}")
            
            # Try multiple selectors for value dropdown
            value_selectors = [
                "//select[@id='value']",
                "//select[contains(@name, 'value')]",
                "//select[contains(@class, 'value')]",
                "//div[contains(@class, 'value')]//select",
                "//select"
            ]
            
            value_selected = False
            for selector in value_selectors:
                try:
                    value_dropdown = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    select = Select(value_dropdown)
                    
                    # Try to select by visible text
                    try:
                        select.select_by_visible_text(f"${target_value} USD")
                        value_selected = True
                        break
                    except:
                        # Try by value attribute
                        try:
                            select.select_by_value(target_value)
                            value_selected = True
                            break
                        except:
                            continue
                except:
                    continue
            
            if not value_selected:
                # Fallback: click on value option directly
                value_options = [
                    f"//option[contains(text(), '${target_value}')]",
                    f"//div[contains(text(), '${target_value}')]",
                    f"//button[contains(text(), '${target_value}')]"
                ]
                
                for option_selector in value_options:
                    try:
                        value_option = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, option_selector))
                        )
                        value_option.click()
                        value_selected = True
                        break
                    except:
                        continue
            
            if value_selected:
                logging.info(f"✅ Selected ${target_value} USD value")
                await self.send_message(f"💰 Selected ${target_value} USD")
                await self.send_screenshot(f"💰 Selected ${target_value} USD Value")
                return True
            else:
                logging.error("❌ Could not select value")
                return False
                
        except Exception as e:
            logging.error(f"❌ Failed to select region and value: {e}")
            await self.send_message(f"❌ Value selection failed: {e}")
            return False
    
    async def click_buy_now(self):
        """Click the Buy Now button"""
        try:
            await self.send_message("🛒 Clicking Buy Now...")
            
            buy_now_selectors = [
                "//button[contains(text(), 'Buy Now')]",
                "//a[contains(text(), 'Buy Now')]",
                "//input[@value='Buy Now']",
                "//button[@type='submit' and contains(., 'Buy')]",
                "//button[contains(@class, 'buy')]",
                "//*[contains(text(), 'Buy Now')]"
            ]
            
            for selector in buy_now_selectors:
                try:
                    buy_button = WebDriverWait(self.driver, 15).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    self.driver.execute_script("arguments[0].click();", buy_button)
                    logging.info("✅ Clicked Buy Now button")
                    await self.send_message("✅ Buy Now clicked")
                    await self.send_screenshot("🛒 Clicked Buy Now Button")
                    
                    # Wait for page transition
                    time.sleep(5)
                    return True
                except Exception as e:
                    continue
            
            logging.error("❌ Could not find Buy Now button")
            return False
        except Exception as e:
            logging.error(f"❌ Failed to click Buy Now: {e}")
            await self.send_message(f"❌ Buy Now failed: {e}")
            return False
    
    async def fill_payment_details(self, card_info: CardInfo):
        """Fill payment details on the payment page"""
        try:
            await self.send_message("📝 Filling payment details...")
            
            # Wait for payment page to load
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Fill email with multiple selector attempts
            email_selectors = [
                "//input[@type='email']",
                "//input[contains(@name, 'email')]",
                "//input[@id='email']",
                "//input[contains(@placeholder, 'email')]"
            ]
            
            email_filled = False
            for selector in email_selectors:
                try:
                    email_field = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    email_field.clear()
                    email_field.send_keys("mail.info.us1@gmail.com")
                    email_filled = True
                    break
                except:
                    continue
            
            if not email_filled:
                logging.warning("⚠️ Could not find email field")
            
            # Select payment card method
            payment_method_selectors = [
                "//input[@value='card']",
                "//input[contains(@name, 'payment') and contains(@value, 'card')]",
                "//label[contains(., 'Payment Card')]//input",
                "//div[contains(., 'Payment Card')]//input",
                "//input[contains(@id, 'card')]"
            ]
            
            payment_selected = False
            for selector in payment_method_selectors:
                try:
                    payment_method = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    self.driver.execute_script("arguments[0].click();", payment_method)
                    payment_selected = True
                    break
                except:
                    continue
            
            if not payment_selected:
                logging.warning("⚠️ Could not select payment card method")
            
            # Click purchase button
            purchase_selectors = [
                "//button[contains(text(), 'Purchase')]",
                "//input[@value='Purchase']",
                "//button[@type='submit' and contains(., 'Purchase')]",
                "//button[contains(@class, 'purchase')]"
            ]
            
            purchase_clicked = False
            for selector in purchase_selectors:
                try:
                    purchase_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    self.driver.execute_script("arguments[0].click();", purchase_button)
                    purchase_clicked = True
                    break
                except:
                    continue
            
            if purchase_clicked:
                await self.send_message("✅ Purchase button clicked")
                await self.send_screenshot("📝 Filled Email & Selected Payment Method")
                
                # Handle checkboxes and confirm
                await self.handle_confirmation()
                
                # Fill card details
                if await self.fill_card_details(card_info):
                    # Fill billing information
                    if await self.fill_billing_info(card_info):
                        # Click place order
                        if await self.click_place_order():
                            return True
            
            return False
        except Exception as e:
            logging.error(f"❌ Failed to fill payment details: {e}")
            await self.send_message(f"❌ Payment details failed: {e}")
            return False
    
    async def handle_confirmation(self):
        """Handle confirmation checkboxes and buttons"""
        try:
            # Wait for confirmation page
            time.sleep(5)
            
            # Find and click all checkboxes
            checkboxes = self.driver.find_elements(By.XPATH, "//input[@type='checkbox']")
            for checkbox in checkboxes:
                try:
                    if not checkbox.is_selected():
                        self.driver.execute_script("arguments[0].click();", checkbox)
                except:
                    continue
            
            # Find and click confirm button
            confirm_selectors = [
                "//button[contains(text(), 'Confirm')]",
                "//input[@value='Confirm']",
                "//button[@type='submit' and contains(., 'Confirm')]",
                "//button[contains(@class, 'confirm')]"
            ]
            
            for selector in confirm_selectors:
                try:
                    confirm_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    self.driver.execute_script("arguments[0].click();", confirm_button)
                    logging.info("✅ Handled confirmation step")
                    await self.send_screenshot("✅ Confirmed Terms & Conditions")
                    break
                except:
                    continue
            
        except Exception as e:
            logging.error(f"❌ Error in confirmation handling: {e}")
    
    async def fill_card_details(self, card_info: CardInfo):
        """Fill card details on payment form"""
        try:
            await self.send_message("💳 Filling card details...")
            
            # Wait for card form to load
            time.sleep(3)
            
            # Map card details to field names with multiple attempts
            field_attempts = [
                # Cardholder name
                [
                    "//input[contains(@name, 'cardholder')]",
                    "//input[contains(@name, 'card_name')]",
                    "//input[contains(@name, 'name_on_card')]",
                    "//input[contains(@placeholder, 'Cardholder')]"
                ],
                # Card number
                [
                    "//input[contains(@name, 'cardnumber')]",
                    "//input[contains(@name, 'card_number')]",
                    "//input[contains(@name, 'number')]",
                    "//input[contains(@placeholder, 'Card Number')]",
                    "//input[@type='tel']"
                ],
                # Expiry date
                [
                    "//input[contains(@name, 'expiry')]",
                    "//input[contains(@name, 'exp_date')]",
                    "//input[contains(@name, 'expiration')]",
                    "//input[contains(@placeholder, 'MM/YY')]"
                ],
                # CVV
                [
                    "//input[contains(@name, 'cvv')]",
                    "//input[contains(@name, 'cvc')]",
                    "//input[contains(@name, 'security_code')]",
                    "//input[contains(@placeholder, 'CVV')]",
                    "//input[contains(@placeholder, 'CVC')]"
                ]
            ]
            
            values = [
                card_info.cardholder_name,
                card_info.card_number.replace(" ", ""),
                card_info.expiry,
                card_info.cvc
            ]
            
            for i, field_group in enumerate(field_attempts):
                field_filled = False
                for selector in field_group:
                    try:
                        field = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        field.clear()
                        
                        # Special handling for expiry date
                        if i == 2:  # Expiry field
                            expiry_clean = card_info.expiry.replace('/', '').strip()
                            if len(expiry_clean) == 4:
                                formatted_expiry = f"{expiry_clean[:2]}/{expiry_clean[2:]}"
                            else:
                                formatted_expiry = expiry_clean
                            field.send_keys(formatted_expiry)
                        else:
                            field.send_keys(values[i])
                        
                        field_filled = True
                        break
                    except:
                        continue
                
                if not field_filled:
                    logging.warning(f"⚠️ Could not fill field group {i}")
            
            logging.info("✅ Filled card details")
            await self.send_screenshot("💳 Filled Card Details")
            return True
        except Exception as e:
            logging.error(f"❌ Error filling card details: {e}")
            await self.send_message(f"❌ Card details failed: {e}")
            return False
    
    def extract_country_from_address(self, billing_address: str) -> str:
        """Extract country from billing address"""
        try:
            if not billing_address:
                return "United States"
            
            # Common country mappings
            country_keywords = {
                'united states': 'United States',
                'usa': 'United States', 
                'us': 'United States',
                'united kingdom': 'United Kingdom',
                'uk': 'United Kingdom',
                'canada': 'Canada',
                'ca': 'Canada',
                'australia': 'Australia',
                'au': 'Australia'
            }
            
            address_lower = billing_address.lower()
            for keyword, country in country_keywords.items():
                if keyword in address_lower:
                    return country
            
            return "United States"
        except Exception as e:
            logging.error(f"❌ Error extracting country: {e}")
            return "United States"
    
    async def fill_billing_info(self, card_info: CardInfo):
        """Fill billing information"""
        try:
            await self.send_message("🏠 Filling billing info...")
            
            # Extract country
            country = self.extract_country_from_address(card_info.billing_address)
            
            # Fill country dropdown
            country_selectors = [
                "//select[contains(@name, 'country')]",
                "//select[contains(@id, 'country')]",
                "//input[contains(@name, 'country')]"
            ]
            
            country_filled = False
            for selector in country_selectors:
                try:
                    country_field = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    
                    if country_field.tag_name == "select":
                        select = Select(country_field)
                        try:
                            select.select_by_visible_text(country)
                            country_filled = True
                            break
                        except:
                            # Try partial match
                            for option in select.options:
                                if country.lower() in option.text.lower():
                                    option.click()
                                    country_filled = True
                                    break
                            if country_filled:
                                break
                    else:
                        country_field.clear()
                        country_field.send_keys(country)
                        country_filled = True
                        break
                except:
                    continue
            
            # Fill name fields if cardholder name exists
            if card_info.cardholder_name:
                names = card_info.cardholder_name.split(' ', 1)
                first_name = names[0]
                last_name = names[1] if len(names) > 1 else ""
                
                # First name
                first_name_selectors = [
                    "//input[contains(@name, 'first')]",
                    "//input[contains(@id, 'first')]",
                    "//input[contains(@placeholder, 'First')]"
                ]
                
                for selector in first_name_selectors:
                    try:
                        field = self.driver.find_element(By.XPATH, selector)
                        field.send_keys(first_name)
                        break
                    except:
                        continue
                
                # Last name
                last_name_selectors = [
                    "//input[contains(@name, 'last')]",
                    "//input[contains(@id, 'last')]",
                    "//input[contains(@placeholder, 'Last')]"
                ]
                
                for selector in last_name_selectors:
                    try:
                        field = self.driver.find_element(By.XPATH, selector)
                        field.send_keys(last_name)
                        break
                    except:
                        continue
            
            logging.info(f"✅ Filled billing information - Country: {country}")
            await self.send_screenshot(f"🏠 Filled Billing Info")
            return True
        except Exception as e:
            logging.error(f"❌ Error filling billing info: {e}")
            await self.send_message(f"❌ Billing info failed: {e}")
            return False
    
    async def click_place_order(self):
        """Click place order button"""
        try:
            await self.send_message("🚀 Clicking Place Order...")
            
            place_order_selectors = [
                "//button[contains(text(), 'Place Order')]",
                "//input[@value='Place Order']",
                "//button[contains(., 'Order') and @type='submit']",
                "//button[contains(., 'Complete Purchase')]",
                "//button[contains(@class, 'place-order')]"
            ]
            
            for selector in place_order_selectors:
                try:
                    place_order_btn = WebDriverWait(self.driver, 15).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    self.driver.execute_script("arguments[0].click();", place_order_btn)
                    logging.info("✅ Clicked Place Order")
                    await self.send_message("✅ Place Order clicked")
                    await self.send_screenshot("🚀 Clicked Place Order Button")
                    
                    # Wait for potential redirect
                    time.sleep(5)
                    return True
                except:
                    continue
            
            return False
        except Exception as e:
            logging.error(f"❌ Error clicking place order: {e}")
            await self.send_message(f"❌ Place order failed: {e}")
            return False
    
    async def handle_otp_page(self):
        """Handle OTP verification page"""
        try:
            await self.send_message("🔐 Checking for OTP page...")
            
            # Wait a bit for page to load
            time.sleep(8)
            
            # Check if OTP field is present
            otp_selectors = [
                "//input[contains(@name, 'otp')]",
                "//input[contains(@id, 'otp')]",
                "//input[contains(@placeholder, 'OTP')]",
                "//input[contains(@type, 'password') and contains(@maxlength, '6')]",
                "//input[contains(@name, 'code')]",
                "//input[contains(@id, 'code')]",
                "//input[contains(@placeholder, 'Code')]",
                "//input[contains(@placeholder, 'Verification')]"
            ]
            
            otp_field = None
            for selector in otp_selectors:
                try:
                    otp_field = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    break
                except:
                    continue
            
            if otp_field and self.otp_info:
                await self.send_message("🎯 OTP page detected - filling code...")
                otp_field.clear()
                otp_field.send_keys(self.otp_info.otp)
                logging.info("✅ Filled OTP code")
                await self.send_screenshot("🔐 Filled OTP Code")
                
                # Find and click submit button
                button_selectors = [
                    "//button[contains(text(), 'Confirm')]",
                    "//button[contains(text(), 'Submit')]",
                    "//button[contains(text(), 'Verify')]",
                    "//input[@type='submit']",
                    "//button[@type='submit']",
                    "//button[contains(@class, 'confirm')]",
                    "//button[contains(@class, 'submit')]"
                ]
                
                for selector in button_selectors:
                    try:
                        button = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        self.driver.execute_script("arguments[0].click();", button)
                        logging.info("✅ Clicked OTP confirmation button")
                        await self.send_message("✅ OTP submitted")
                        await self.send_screenshot("✅ Submitted OTP")
                        return True
                    except:
                        continue
                
                return True
            else:
                logging.info("ℹ️ No OTP page detected or no OTP available")
                return False
        except Exception as e:
            logging.error(f"❌ Error handling OTP page: {e}")
            return False
    
    async def check_transaction_status(self):
        """Check and report transaction status"""
        try:
            await self.send_message("📊 Checking transaction status...")
            
            # Wait for status to stabilize
            time.sleep(10)
            
            page_source = self.driver.page_source.lower()
            current_url = self.driver.current_url
            
            status = "Unknown"
            status_message = ""
            
            success_keywords = ['success', 'confirmed', 'completed', 'thank you', 'approved', 'payment successful']
            fail_keywords = ['fail', 'error', 'declined', 'rejected', 'invalid', 'unsuccessful']
            pending_keywords = ['pending', 'processing', 'waiting']
            
            if any(word in page_source for word in success_keywords):
                status = "SUCCESS"
                status_message = "🎉 TRANSACTION SUCCESSFUL!"
            elif any(word in page_source for word in fail_keywords):
                status = "FAILED" 
                status_message = "❌ TRANSACTION FAILED"
            elif any(word in page_source for word in pending_keywords):
                status = "PENDING"
                status_message = "⏳ Transaction Pending"
            else:
                status = "UNKNOWN"
                status_message = "❓ Status Unknown"
            
            # Get page title for additional info
            page_title = self.driver.title
            
            full_status = f"""
📊 TRANSACTION RESULT:
Status: {status_message}
Page Title: {page_title}
URL: {current_url}
Transaction Count: {self.transaction_count + 1}
            """.strip()
            
            logging.info(f"Transaction Status: {status}")
            await self.send_message(full_status)
            await self.send_screenshot(f"📊 FINAL STATUS: {status}")
            
            return status
        except Exception as e:
            logging.error(f"❌ Error checking transaction status: {e}")
            await self.send_message(f"❌ Status check failed: {e}")
            return "ERROR"
    
    async def process_card(self, card_info: CardInfo):
        """Main method to process a card through the entire flow"""
        try:
            self.transaction_count = 0
            success_count = 0
            
            await self.send_message(f"""
🔄 STARTING AUTOMATION
Card: {card_info.card_number[-4:]}
Type: {card_info.card_type}
First Amount: {'$500' if card_info.card_type.lower() == 'mastercard' else '$100'}
            """.strip())
            
            while self.running:
                self.transaction_count += 1
                current_amount = "$500" if (card_info.card_type.lower() == "mastercard" and self.transaction_count == 1) else "$100"
                
                await self.send_message(f"""
💳 TRANSACTION #{self.transaction_count}
Card: {card_info.card_number[-4:]}
Amount: {current_amount}
                """.strip())
                
                # Reset OTP info for new transaction
                if self.transaction_count > 1:
                    self.otp_info = None
                
                # Navigate to gift card page
                if not await self.navigate_to_giftcard_page():
                    break
                
                # Select region and value
                if not await self.select_region_and_value(card_info.card_type):
                    break
                
                # Click buy now
                if not await self.click_buy_now():
                    break
                
                # Fill payment details
                if not await self.fill_payment_details(card_info):
                    break
                
                # Handle OTP if present
                otp_required = await self.handle_otp_page()
                
                # Check transaction status
                status = await self.check_transaction_status()
                
                if status == "SUCCESS":
                    success_count += 1
                    await self.send_message(f"✅ Transaction #{self.transaction_count} SUCCESSFUL!")
                    
                    # Check for mastercard rules
                    if card_info.card_type.lower() == "mastercard":
                        if self.transaction_count == 1 and otp_required:
                            await self.send_message("🛑 Mastercard: OTP required on first transaction - stopping")
                            break
                        elif self.transaction_count > 1 and otp_required:
                            await self.send_message("🛑 Mastercard: OTP required on subsequent transaction - stopping")
                            break
                
                elif status == "FAILED":
                    await self.send_message(f"❌ Transaction #{self.transaction_count} FAILED - stopping")
                    break
                
                # Small delay between transactions
                if self.running:
                    await self.send_message("⏳ Preparing next transaction...")
                    time.sleep(10)
            
            # Final summary
            await self.send_message(f"""
📈 AUTOMATION COMPLETED
Card: {card_info.card_number[-4:]}
Total Transactions: {self.transaction_count}
Successful: {success_count}
            """.strip())
            
            return success_count > 0
        except Exception as e:
            logging.error(f"❌ Error processing card: {e}")
            await self.send_message(f"❌ Automation error: {e}")
            return False

class EmailChecker:
    def __init__(self):
        self.email = "mail.info.us1@gmail.com"
        self.password = "hsrfarffbbppocqv"
    
    def check_delivery_status(self):
        """Check email for delivery status"""
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(self.email, self.password)
            mail.select("inbox")
            
            status, messages = mail.search(None, 'UNSEEN')
            email_ids = messages[0].split()
            
            delivery_found = False
            delivery_info = []
            
            for email_id in email_ids:
                status, msg_data = mail.fetch(email_id, "(RFC822)")
                email_body = msg_data[0][1]
                message = email.message_from_bytes(email_body)
                
                subject = decode_header(message["subject"])[0][0]
                if isinstance(subject, bytes):
                    subject = subject.decode()
                
                # Check for delivery-related keywords
                delivery_keywords = ['delivered', 'gift card', 'razer', 'coinbase', 'coingate', 'payment', 'success']
                
                if any(keyword in subject.lower() for keyword in delivery_keywords):
                    # Mark as read
                    mail.store(email_id, '+FLAGS', '\\Seen')
                    delivery_found = True
                    delivery_info.append(f"📧 {subject}")
            
            mail.close()
            mail.logout()
            
            if delivery_found:
                return "✅ New delivery emails:\n" + "\n".join(delivery_info)
            else:
                return "❌ No new delivery emails"
        except Exception as e:
            logging.error(f"❌ Error checking email: {e}")
            return f"❌ Email check error: {e}"

class TelegramBotHandler:
    def __init__(self):
        self.token = "8594532460:AAFiJ3-ip3xqcx394T8soMx8C2gscOqC7pA"
        self.application = Application.builder().token(self.token).build()
        self.automation = None
        self.email_checker = EmailChecker()
        self.current_card_thread = None
        self.is_processing = False
    
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text("""
🤖 CC SPENDING BOT READY

Commands:
• Send card in format to start automation
• Send OTP when required
• /status - Check bot status  
• /stop - Stop automation
• /check_email - Check deliveries
• /screenshot - Get current page

Format for card:
💳 New Card Added
👤 Cardholder Name: 
💳 Card Number: 
🏦 Card Type: 
📅 Expiry: 
🔐 CVC: 
🏠 Billing Address: 
⏰ Time: 
        """.strip())
    
    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        if self.automation:
            status = "🟢 RUNNING" if self.automation.running else "🔴 STOPPED"
            processing = "🔄 PROCESSING" if self.is_processing else "⏸️ IDLE"
            await update.message.reply_text(f"""
🤖 BOT STATUS
Automation: {status}
Processing: {processing}
Transactions: {self.automation.transaction_count}
Current Card: {self.automation.current_card.card_number[-4:] if self.automation.current_card else 'None'}
            """.strip())
        else:
            await update.message.reply_text("❌ No active automation session")
    
    async def handle_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop command"""
        if self.automation and self.is_processing:
            self.automation.running = False
            self.is_processing = False
            await update.message.reply_text("🛑 Automation stopped")
        else:
            await update.message.reply_text("❌ No active automation to stop")
    
    async def handle_check_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /check_email command"""
        email_status = self.email_checker.check_delivery_status()
        await update.message.reply_text(f"📧 {email_status}")
    
    async def handle_screenshot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /screenshot command"""
        if self.automation and self.automation.driver and self.is_processing:
            await self.automation.send_screenshot("📸 Manual Screenshot Request")
        else:
            await update.message.reply_text("❌ No active automation session for screenshot")
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages (non-command)"""
        try:
            message_text = update.message.text
            chat_id = update.effective_chat.id
            
            logging.info(f"📨 Received message: {message_text[:100]}...")
            
            if "💳 new card added" in message_text.lower():
                if self.is_processing:
                    await update.message.reply_text("❌ Automation already in progress. Please wait for current card to finish.")
                    return
                
                # Initialize automation with bot and chat_id
                self.automation = CoinGateAutomation(
                    telegram_bot=self.application.bot,
                    chat_id=chat_id
                )
                
                card_info = self.automation.extract_card_info(message_text)
                if card_info:
                    self.automation.current_card = card_info
                    self.automation.running = True
                    self.automation.otp_info = None
                    self.is_processing = True
                    
                    # Stop any existing automation
                    if self.current_card_thread and self.current_card_thread.is_alive():
                        self.automation.running = False
                        self.current_card_thread.join(timeout=10)
                    
                    # FIXED: Create a new event loop for the thread
                    def run_automation():
                        try:
                            # Create new event loop for this thread
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            
                            # Run the automation
                            loop.run_until_complete(self.automation.process_card(card_info))
                            loop.close()
                        except Exception as e:
                            logging.error(f"❌ Automation thread error: {e}")
                        finally:
                            self.is_processing = False
                    
                    self.current_card_thread = threading.Thread(target=run_automation)
                    self.current_card_thread.daemon = True
                    self.current_card_thread.start()
                    
                    await update.message.reply_text(f"""
✅ CARD RECEIVED & PROCESSING STARTED
Card: {card_info.card_number[-4:]}
Type: {card_info.card_type}
First Amount: {'$500' if card_info.card_type.lower() == 'mastercard' else '$100'}
                    """.strip())
                    
                    # Send immediate confirmation and debug info
                    await self.automation.send_message("🚀 Automation thread started successfully!")
                    await self.automation.send_message("🔧 Checking driver status...")
                    await self.automation.debug_check_driver()
                else:
                    await update.message.reply_text("❌ Failed to parse card information. Please check the format.")
            
            elif "🔐 card verification otp" in message_text.lower():
                if self.automation and self.is_processing:
                    otp_info = self.automation.extract_otp_info(message_text)
                    if otp_info:
                        self.automation.otp_info = otp_info
                        await update.message.reply_text(f"🔑 OTP received for card: {otp_info.card_number[-4:]}")
                    else:
                        await update.message.reply_text("❌ Failed to parse OTP information")
                else:
                    await update.message.reply_text("❌ No active automation session to use OTP")
                
        except Exception as e:
            logging.error(f"❌ Error handling Telegram message: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")

    def start_bot(self):
        """Start the Telegram bot with proper command handlers"""
        # Add command handlers
        self.application.add_handler(CommandHandler("start", self.handle_start))
        self.application.add_handler(CommandHandler("status", self.handle_status))
        self.application.add_handler(CommandHandler("stop", self.handle_stop))
        self.application.add_handler(CommandHandler("check_email", self.handle_check_email))
        self.application.add_handler(CommandHandler("screenshot", self.handle_screenshot))
        
        # Add text message handler for cards and OTP
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        
        logging.info("🤖 Starting Telegram bot on Render...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

def main():
    """Main function to start the application"""
    logging.info("🚀 Starting CC Spending Bot on Render...")
    
    try:
        bot_handler = TelegramBotHandler()
        bot_handler.start_bot()
        
    except Exception as e:
        logging.error(f"❌ Application error: {e}")

if __name__ == "__main__":
    main()