import os
import secrets
import validators
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from supabase import create_client, Client
from dotenv import load_dotenv
import qrcode
from io import BytesIO
import base64
import logging

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Supabase
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase = create_client(supabase_url, supabase_key)


def generate_random_code(length=6):
    """Generate a random alphanumeric code"""
    return secrets.token_urlsafe(length)[:length]


def validate_custom_code(code):
    """Validate custom short code"""
    return code.isalnum() and 3 <= len(code) <= 20


def create_qr_code(url):
    """Generate QR code and return as base64"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')


def normalize_url(url):
    """Ensure URL has proper scheme and format"""
    url = url.strip()
    if not url:
        return None

    # Add scheme if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # Remove any whitespace or invalid characters
    url = ''.join(url.split())
    return url.lower()


def is_valid_url(url):
    """Comprehensive URL validation"""
    try:
        return validators.url(url)
    except validators.ValidationError:
        return False


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        original_url = normalize_url(request.form.get('url'))
        custom_code = request.form.get('custom_code', '').strip()

        # Validate URL
        if not original_url or not is_valid_url(original_url):
            flash('Please enter a valid URL (e.g., https://example.com)', 'error')
            return redirect(url_for('index'))

        # Generate or validate custom code
        if custom_code:
            if not validate_custom_code(custom_code):
                flash('Custom code must be 3-20 alphanumeric characters', 'error')
                return redirect(url_for('index'))
            short_code = custom_code
        else:
            short_code = generate_random_code()

            # Ensure code is unique (try up to 5 times)
            attempts = 0
            while attempts < 5:
                existing = supabase.table('urls').select('short_code').eq('short_code', short_code).execute()
                if not existing.data:
                    break
                short_code = generate_random_code()
                attempts += 1
            else:
                flash('Could not generate a unique short code. Please try again.', 'error')
                return redirect(url_for('index'))

        # Insert into database
        try:
            response = supabase.table('urls').insert({
                'original_url': original_url,
                'short_code': short_code,
                'created_at': datetime.utcnow().isoformat(),
                'clicks': 0
            }).execute()

            if response.data:
                short_url = f"{request.host_url.rstrip('/')}/{short_code}"
                qr_code = create_qr_code(short_url)
                return render_template('index.html',
                                       short_url=short_url,
                                       qr_code=qr_code,
                                       original_url=original_url)

        except Exception as e:
            logger.error(f"Database insert error: {str(e)}")
            if 'duplicate key value' in str(e):
                flash('That custom code is already in use. Please try another one.', 'error')
            else:
                flash('An error occurred. Please try again.', 'error')
            return redirect(url_for('index'))

    return render_template('index.html')


@app.route('/<short_code>')
def redirect_url(short_code):
    try:
        logger.info(f"Attempting redirect for code: {short_code}")

        # Fetch the URL from Supabase with better error handling
        response = supabase.table('urls') \
            .select('original_url') \
            .eq('short_code', short_code) \
            .maybe_single() \
            .execute()

        # Debugging: Print the full response
        logger.debug(f"Supabase response: {response}")

        if response.data and 'original_url' in response.data:
            original_url = response.data['original_url']

            # Ensure URL has proper scheme
            if not original_url.startswith(('http://', 'https://')):
                original_url = f'https://{original_url}'

            logger.info(f"Redirecting to: {original_url}")

            # Update click count (non-blocking)
            try:
                supabase.table('urls') \
                    .update({'clicks': supabase.rpc('increment')}) \
                    .eq('short_code', short_code) \
                    .execute()
            except Exception as e:
                logger.error(f"Click count update failed: {str(e)}")
                # Don't fail redirect if click update fails

            return redirect(original_url, code=302)

        logger.warning(f"Short code not found: {short_code}")
        flash('Short URL not found', 'error')
        return render_template('error.html', error="URL not found"), 404

    except Exception as e:
        logger.error(f"Redirect failed: {str(e)}", exc_info=True)
        flash('Redirect error occurred', 'error')
        return render_template('error.html', error="Redirect failed"), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)