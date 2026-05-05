import os
import logging
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
_secret = os.environ.get('FLASK_SECRET_KEY')
if not _secret:
    raise RuntimeError("FLASK_SECRET_KEY environment variable is not set. Refusing to start.")
app.secret_key = _secret

# ── Supabase clients ──
SUPABASE_URL         = os.environ.get('SUPABASE_URL')
SUPABASE_KEY         = os.environ.get('SUPABASE_KEY')          # anon key  (public)
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY')  # service-role key (secret, backend-only)

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set.")
if not SUPABASE_SERVICE_KEY:
    raise RuntimeError("SUPABASE_SERVICE_KEY must be set (required for admin operations).")

# Regular client — used for auth sign-in / sign-up
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Admin client — service-role key bypasses RLS; NEVER expose to the browser
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# ── Helper ──
def get_current_user():
    return session.get('user')


# ════════════════════════════════
#  AUTH ROUTES
# ════════════════════════════════

@app.route('/')
def root():
    if get_current_user():
        return redirect(url_for('todo'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if get_current_user():
        return redirect(url_for('todo'))

    if request.method == 'POST':
        data     = request.get_json(silent=True) or {}
        email    = data.get('email', '').strip()
        password = data.get('password', '').strip()

        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password are required.'}), 400

        try:
            response = supabase.auth.sign_in_with_password({'email': email, 'password': password})
            user = response.user

            if not user:
                return jsonify({'success': False, 'message': 'Invalid email or password.'}), 401

            # Use admin client so RLS doesn't block the profile lookup
            profile = supabase_admin.table("profiles").select("*").eq("id", str(user.id)).execute()
            role = profile.data[0]['role'] if profile.data else 'user'

            session['user'] = {
                'id':    str(user.id),
                'email': user.email,
                'role':  role,
            }
            return jsonify({'success': True, 'redirect': '/todo'})

        except Exception as e:
            logger.warning(f"Login failed for {email}: {e}")
            return jsonify({'success': False, 'message': 'Invalid email or password.'}), 401

    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if get_current_user():
        return redirect(url_for('todo'))

    if request.method == 'POST':
        data     = request.get_json(silent=True) or {}
        email    = data.get('email', '').strip()
        password = data.get('password', '').strip()

        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password are required.'}), 400
        if len(password) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters.'}), 400

        try:
            response = supabase.auth.sign_up({'email': email, 'password': password})
            user = response.user
            if user:
                # Use admin client to insert profile (bypasses RLS)
                supabase_admin.table("profiles").insert({
                    "id":    str(user.id),
                    "email": user.email,
                    "role":  "user",
                }).execute()
            return jsonify({
                'success': True,
                'message': 'Account created! Please check your email to confirm, then log in.'
            })
        except Exception as e:
            logger.error(f"Signup error for {email}: {e}")
            msg = str(e) if str(e) else 'Signup failed. Please try again.'
            return jsonify({'success': False, 'message': msg}), 400

    return render_template('signup.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ════════════════════════════════
#  PROTECTED TODO PAGE
# ════════════════════════════════

@app.route('/todo')
def todo():
    if not get_current_user():
        return redirect(url_for('login'))
    user = get_current_user()
    return render_template('index.html', email=user['email'],
        role=user['role']
        )


# ════════════════════════════════
#  TASK API  (all protected)
# ════════════════════════════════

def require_login():
    """Returns (user, None) or (None, error_response)."""
    user = get_current_user()
    if not user:
        return None, (jsonify({'error': 'Unauthorized'}), 401)
    return user, None


@app.route('/tasks', methods=['GET'])
def get_tasks():
    user, err = require_login()
    if err:
        return err

    response = (
        supabase_admin.table('tasks')
        .select('*')
        .eq('user_id', user['id'])
        .order('created_at', desc=False)
        .execute()
    )
    return jsonify({'tasks': response.data})


@app.route('/tasks', methods=['POST'])
def add_task():
    user, err = require_login()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Task text is required'}), 400

    response = (
        supabase_admin.table('tasks')
        .insert({'user_id': user['id'], 'text': text, 'completed': False})
        .execute()
    )
    return jsonify({'task': response.data[0]}), 201


# ── task_id is a UUID string (no <int:> prefix) ──
@app.route('/tasks/<task_id>', methods=['PUT'])
def update_task(task_id):
    user, err = require_login()
    if err:
        return err

    data    = request.get_json(silent=True) or {}
    updates = {}
    if 'completed' in data:
        updates['completed'] = data['completed']
    if 'text' in data:
        updates['text'] = data['text']

    if not updates:
        return jsonify({'error': 'Nothing to update'}), 400

    response = (
        supabase_admin.table('tasks')
        .update(updates)
        .eq('id', task_id)
        .eq('user_id', user['id'])
        .execute()
    )
    if not response.data:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify({'task': response.data[0]})


@app.route('/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    user, err = require_login()
    if err:
        return err

    supabase_admin.table('tasks').delete().eq('id', task_id).eq('user_id', user['id']).execute()
    return jsonify({'message': 'Task deleted'})


@app.route('/tasks/clear-completed', methods=['DELETE'])
def clear_completed():
    user, err = require_login()
    if err:
        return err

    supabase_admin.table('tasks').delete().eq('user_id', user['id']).eq('completed', True).execute()
    return jsonify({'message': 'Cleared completed tasks'})


# ════════════════════════════════
#  ADMIN PANEL
# ════════════════════════════════

def require_admin_page():
    """For page routes — redirect on failure."""
    user = get_current_user()
    if not user:
        return None, redirect(url_for('login'))
    if user.get('role') != 'admin':
        return None, redirect(url_for('todo'))
    return user, None


def require_admin_api():
    """For API/JSON routes — return JSON error on failure."""
    user = get_current_user()
    if not user:
        return None, (jsonify({'error': 'Unauthorized'}), 401)
    if user.get('role') != 'admin':
        return None, (jsonify({'error': 'Forbidden'}), 403)
    return user, None


@app.route('/admin')
def admin():
    user, err = require_admin_page()
    if err:
        return err

    profiles  = supabase_admin.table("profiles").select("*").order("email").execute()
    all_tasks = supabase_admin.table("tasks").select("*").order("created_at", desc=False).execute()

    tasks_by_user = {}
    for task in all_tasks.data:
        uid = task['user_id']
        tasks_by_user.setdefault(uid, []).append(task)

    return render_template(
        'admin.html',
        users=profiles.data,
        tasks_by_user=tasks_by_user,
        email=user['email'],
    )


@app.route('/admin/delete-user/<user_id>', methods=['DELETE'])
def admin_delete_user(user_id):
    _, err = require_admin_api()   # ← returns JSON, not redirect
    if err:
        return err

    try:
        supabase_admin.table("tasks").delete().eq("user_id", user_id).execute()
        supabase_admin.table("profiles").delete().eq("id", user_id).execute()
        supabase_admin.auth.admin.delete_user(user_id)  # requires service-role key
        return jsonify({'success': True, 'message': 'User deleted.'})
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


# ════════════════════════════════
#  MISC
# ════════════════════════════════

@app.route('/robots.txt')
def robots():
    robots_path = os.path.join(os.path.dirname(__file__), 'robots.txt')
    if not os.path.exists(robots_path):
        return "User-agent: *\nDisallow:\n", 200, {'Content-Type': 'text/plain'}
    return send_from_directory(os.path.dirname(__file__), 'robots.txt')


if __name__ == '__main__':
    app.run(debug=False)
