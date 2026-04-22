"""
WhatsApp Notification Service — WAPilot API Integration
Sends appointment notifications and messages to patients via WhatsApp.

Documentation: https://app.wapilot.net/api-doc/v2
Provider: WAPilot (Third-party WhatsApp Service)
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

# ── Configuration (read from environment) ──────────────────────────────────
# WAPilot API Configuration
WAPILOT_API_TOKEN = os.environ.get('WAPILOT_API_TOKEN', '5Y0xDV1v9lue5IkAOpqeWueA4diPypoy4ZvaEphq4e')
WAPILOT_INSTANCE_ID = os.environ.get('WAPILOT_INSTANCE_ID', 'instance3809')
SITE_URL = os.environ.get('SITE_URL', 'https://alteb.almarkazy.com')


WAPILOT_API_URL = f"https://api.wapilot.net/api/v2/{WAPILOT_INSTANCE_ID}/send-message"


def _format_phone_for_whatsapp(phone: str) -> str:
    """
    Convert a local Egyptian phone number to international format for WhatsApp.
    Examples:
        '01550010435'  →  '201550010435'
        '1550010435'   →  '201550010435'
        '201550010435' →  '201550010435'  (already international)
    """
    if not phone:
        return ''
    
    # Remove any spaces, dashes, or plus signs
    phone = phone.strip().replace(' ', '').replace('-', '').replace('+', '')
    
    # Already in international format (starts with 20 and is 12 digits)
    if phone.startswith('20') and len(phone) == 12:
        return phone
    
    # Local format starting with 0 (e.g., 01550010435)
    if phone.startswith('0') and len(phone) == 11:
        return '20' + phone[1:]
    
    # Without leading zero (e.g., 1550010435)
    if len(phone) == 10 and not phone.startswith('0'):
        return '20' + phone
    
    # Fallback: return as-is (let WAPilot API handle validation)
    return phone


def send_appointment_whatsapp(
    patient_phone: str,
    clinic_name: str,
    doctor_name: str,
    appointment_date: str,
    appointment_time: str,
    auto_lookup_url: str,
    priority: int = None,
    send_at: str = None
) -> dict:
    """
    Send appointment confirmation via WhatsApp using WAPilot API.
    
    Args:
        patient_phone: Patient's phone number (local or international)
        clinic_name: Name of the clinic
        doctor_name: Name of the doctor
        appointment_date: Formatted appointment date string
        appointment_time: Formatted appointment time string
        auto_lookup_url: Full URL for auto-lookup (e.g., https://alteb.almarkazy.com/patient/auto/TOKEN)
        priority: Optional queue priority (min 0). Higher = sooner delivery
        send_at: Optional ISO 8601 datetime to schedule message (e.g., "2026-04-25T10:30:00Z")
    
    Returns:
        dict with 'success' (bool) and 'message_id' or 'error'
    """
    # Validate configuration
    if not WAPILOT_API_TOKEN or not WAPILOT_INSTANCE_ID:
        logger.warning("WAPILOT_API_TOKEN or WAPILOT_INSTANCE_ID not configured — skipping WhatsApp notification")
        return {'success': False, 'error': 'WAPilot API credentials not configured'}
    
    formatted_phone = _format_phone_for_whatsapp(patient_phone)
    if not formatted_phone:
        logger.warning(f"Invalid phone number: {patient_phone}")
        return {'success': False, 'error': 'Invalid phone number'}
    
    # Build chat_id in WAPilot format (e.g., "201550010435@s.whatsapp.net")
    chat_id = f"{formatted_phone}@s.whatsapp.net"
    
    # Build formatted text message with appointment details
    message_text = (
        f"مرحباً بك في {clinic_name}\n\n"
        f"تم حجز موعدك بنجاح:\n"
        f"📅 التاريخ: {appointment_date}\n"
        f"🕐 الوقت: {appointment_time}\n"
        f"👨‍⚕️ الدكتور: {doctor_name}\n\n"
        f"حفاظا على وقتك تابع دورك ومعاد حضورك لايف :\n"
        f"{auto_lookup_url}"
    )
    
    # Validate message length
    if len(message_text) > 4096:
        logger.error(f"❌ Message exceeds WAPilot limit (4096): {len(message_text)} chars")
        return {'success': False, 'error': 'Message text exceeds maximum length (4096 characters)'}
    
    headers = {
        'token': WAPILOT_API_TOKEN,
        'Content-Type': 'application/json'
    }
    
    # Build payload with required and optional parameters
    payload = {
        "chat_id": chat_id,
        "text": message_text
    }
    
    # Add optional parameters if provided
    if priority is not None and priority >= 0:
        payload["priority"] = priority
    
    if send_at is not None:
        payload["send_at"] = send_at
    
    try:
        response = requests.post(WAPILOT_API_URL, json=payload, headers=headers, timeout=10)
        response_data = response.json()
        
        # Success: 200
        if response.status_code == 200:
            msg_id = response_data.get('id') or response_data.get('message_id') or response_data.get('data', {}).get('id')
            logger.info(f"✅ WhatsApp sent to {formatted_phone} (chat_id: {chat_id}) — message_id: {msg_id}")
            return {
                'success': True,
                'message_id': msg_id,
                'status': response_data.get('status', 'sent'),
                'response': response_data
            }
        
        # Error handling for various status codes
        elif response.status_code == 400:
            error_details = response_data.get('error', response_data.get('message', 'Bad request'))
            logger.error(f"❌ WAPilot validation error (400): {error_details}")
            return {'success': False, 'error': f'Invalid request: {error_details}'}
        
        elif response.status_code == 401:
            logger.error(f"❌ WAPilot authentication failed (401) — check token and instance_id")
            return {'success': False, 'error': 'Authentication failed: Invalid token or instance'}
        
        elif response.status_code == 422:
            error_details = response_data.get('error', response_data.get('message', 'Unprocessable entity'))
            logger.error(f"❌ WAPilot unprocessable entity (422): {error_details}")
            return {'success': False, 'error': f'Message validation failed: {error_details}'}
        
        elif response.status_code == 429:
            logger.error(f"❌ WAPilot rate limit exceeded (429) — try again later")
            return {'success': False, 'error': 'Rate limit exceeded: Too many requests'}
        
        elif response.status_code == 500:
            logger.error(f"❌ WAPilot server error (500)")
            return {'success': False, 'error': 'Server error: WAPilot API unavailable'}
        
        else:
            error_msg = response_data.get('error', {}).get('message') if isinstance(response_data.get('error'), dict) else response_data.get('error', response.text)
            logger.error(f"❌ WAPilot API error ({response.status_code}): {error_msg}")
            return {'success': False, 'error': f'API error ({response.status_code}): {error_msg}'}
    
    except requests.exceptions.Timeout:
        logger.error(f"❌ WAPilot API timeout for {formatted_phone}")
        return {'success': False, 'error': 'API request timed out (10 seconds)'}
    
    except requests.exceptions.ConnectionError as e:
        logger.error(f"❌ WAPilot connection error: {str(e)}")
        return {'success': False, 'error': f'Connection error: {str(e)}'}
    
    except ValueError as e:
        logger.error(f"❌ Invalid JSON response from WAPilot: {str(e)}")
        return {'success': False, 'error': 'Invalid API response'}
    
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ WAPilot API request failed: {str(e)}")
        return {'success': False, 'error': str(e)}


def build_auto_lookup_url(lookup_token: str) -> str:
    """Build the full auto-lookup URL for a visit."""
    base_url = SITE_URL.rstrip('/')
    return f"{base_url}/patient/auto/{lookup_token}"


def send_text_message(
    patient_phone: str,
    message_text: str,
    priority: int = None,
    send_at: str = None
) -> dict:
    """
    Send a simple text message via WAPilot.
    
    Args:
        patient_phone: Recipient phone number
        message_text: Message text (max 4096 chars)
        priority: Optional queue priority
        send_at: Optional ISO 8601 datetime to schedule
    
    Returns:
        dict with 'success' and 'message_id' or 'error'
    """
    if not WAPILOT_API_TOKEN or not WAPILOT_INSTANCE_ID:
        logger.warning("WAPilot credentials not configured")
        return {'success': False, 'error': 'WAPilot API credentials not configured'}
    
    formatted_phone = _format_phone_for_whatsapp(patient_phone)
    if not formatted_phone:
        return {'success': False, 'error': 'Invalid phone number'}
    
    if len(message_text) > 4096:
        return {'success': False, 'error': 'Message exceeds maximum length (4096 characters)'}
    
    chat_id = f"{formatted_phone}@s.whatsapp.net"
    
    headers = {
        'token': WAPILOT_API_TOKEN,
        'Content-Type': 'application/json'
    }
    
    payload = {
        "chat_id": chat_id,
        "text": message_text
    }
    
    if priority is not None and priority >= 0:
        payload["priority"] = priority
    
    if send_at is not None:
        payload["send_at"] = send_at
    
    try:
        response = requests.post(WAPILOT_API_URL, json=payload, headers=headers, timeout=10)
        response_data = response.json()
        
        if response.status_code == 200:
            msg_id = response_data.get('id') or response_data.get('message_id')
            logger.info(f"✅ Text message sent to {formatted_phone} — id: {msg_id}")
            return {'success': True, 'message_id': msg_id, 'response': response_data}
        else:
            logger.error(f"❌ API error ({response.status_code}): {response_data}")
            return {'success': False, 'error': str(response_data)}
    
    except Exception as e:
        logger.error(f"❌ Failed to send message: {str(e)}")
        return {'success': False, 'error': str(e)}


def get_instance_status() -> dict:
    """
    Check WAPilot instance status.
    
    Returns:
        dict with instance status information
    """
    if not WAPILOT_API_TOKEN or not WAPILOT_INSTANCE_ID:
        return {'success': False, 'error': 'WAPilot credentials not configured'}
    
    status_url = f"https://api.wapilot.net/api/v2/instances/{WAPILOT_INSTANCE_ID}/status"
    
    headers = {
        'token': WAPILOT_API_TOKEN,
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(status_url, headers=headers, timeout=5)
        response_data = response.json()
        
        if response.status_code == 200:
            logger.info(f"✅ Instance status: {response_data}")
            return {'success': True, 'status': response_data}
        else:
            logger.error(f"❌ Status check failed: {response_data}")
            return {'success': False, 'error': response_data}
    
    except Exception as e:
        logger.error(f"❌ Failed to check instance status: {str(e)}")
        return {'success': False, 'error': str(e)}
