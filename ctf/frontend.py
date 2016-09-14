""" Native Front End """
from functools import wraps
from flask import Blueprint, request, session, abort, redirect, \
                  render_template, url_for, flash, send_from_directory
from flask_wtf.csrf import validate_csrf
from . import core
from ._compat import urlparse
from .core import CtfException
from .forms import CreateForm, LoginForm, TeamForm, SubmitForm


bp = Blueprint('frontend', __name__)


def is_safe_url(url):
    """Determine whether a URL is safe for redirection."""
    u = urlparse(url)
    return u.scheme == '' and u.netloc == '' and u.path != request.path


def ensure_user(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        user = None
        if 'key' in session:
            user = core.user_for_token(session['key'])
        if user is None:
            flash('You must be logged in to do that.', 'danger')
            return redirect(url_for('.login', next=request.path), code=303)
        return fn(user, *args, **kwargs)
    return inner


def ensure_team(fn):
    @ensure_user
    @wraps(fn)
    def inner(user, *args, **kwargs):
        if user.team is None:
            flash('You must be part of a team.', 'danger')
            return redirect(url_for('.home_page'), code=303)
        return fn(user.team, *args, **kwargs)
    return inner


@bp.route('/')
def home_page():
    name = core.get_name()
    teams = core.get_teams()
    return render_template('home.html', name=name, teams=teams)


@bp.route('/challenges/')
@ensure_team
def challenge_page(team):
    name = core.get_name()
    challenges = core.get_challenges(team)
    resource_urls = {}
    for c in challenges:
        for r in c.resources:
            resource_urls[r.name] = url_for('.get_resource',
                                             category = c.category,
                                             name = r.name)
    print resource_urls
    return render_template('challenge.html', name=name, challenges=challenges,
                            resource_urls=resource_urls)


@bp.route('/teams/<int:id>/')
def team_page(id):
    """Get the page for a specific team."""
    name = core.get_name()
    team = core.get_team(id)
    if not team:
        abort(404)
    categories = []
    return render_template('team.html', name=name, team=team,
                           categories=categories)


def redirect_next(fallback, **kwargs):
    url = request.args.get('next')
    if not url or not is_safe_url(url):
        url = fallback
    return redirect(url, **kwargs)


def flash_wtf_errors(form):
    for field, errors in form.errors.items():
        for error in errors:
            flash("%s: %s" % (getattr(form, field).label.text, error),
                  'danger')


@bp.route('/register/', methods=['GET', 'POST'])
def create_user():
    code = 200
    name = core.get_name()
    form = CreateForm()

    if form.validate_on_submit():
        try:
            user = core.create_user(form.username.data, form.password.data)
        except CtfException as exc:
            flash(exc.message, 'danger')
            code = 409
        else:
            key = core.create_session_key(user)
            session['key'] = key
            return redirect_next(fallback=url_for('.home_page'), code=303)
    elif request.method == 'POST':
        # Attempted submit, but form validation failed
        code = 400

    flash_wtf_errors(form)
    return render_template('register.html', name=name, form=form), code


@bp.route('/team/', methods=['GET', 'POST'])
@ensure_user
def manage_team(user):
    code = 200
    name = core.get_name()
    form = TeamForm()
    if user.team is not None:
        return redirect(url_for('.team_page', id=user.team.id), code=303)

    if form.validate_on_submit():
        try:
            core.create_team(user, form.name.data)
        except CtfException as exc:
            flash(exc.message, 'danger')
            code = 409
        else:
            return redirect(url_for('.home_page'), code=303)
    elif request.method == 'POST':
        # Attempted submit, but form validation failed
        code = 400

    flash_wtf_errors(form)
    return render_template('create_team.html', name=name, form=form), code


@bp.route('/login/', methods=['GET', 'POST'])
def login():
    """Log into a team with its password."""
    code = 200
    name = core.get_name()
    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = core.login(form.username.data, form.password.data)
        except CtfException as exc:
            flash(exc.message, 'danger')
            code = 403
        else:
            key = core.create_session_key(user)
            session['key'] = key
            return redirect_next(fallback=url_for('.home_page'), code=303)
    flash_wtf_errors(form)
    return render_template('login.html', name=name, form=form), code


@bp.route('/logout/')
@ensure_user
def logout(user):
    """Clear the session, and redirect to home."""
    if not validate_csrf(request.args.get('token', '')):
        flash('Missing or incorrect CSRF token.')
        abort(400)
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('.home_page'), code=303)


@bp.route('/passwords.zip')
def snoopin():
    return redirect('https://www.youtube.com/watch?v=dQw4w9WgXcQ', code=303)


@bp.route('/submit/', methods=['GET', 'POST'])
@ensure_team
def submit_fleg(team):
    """Attempt to submit a fleg, and redirect to the fleg page."""
    form = SubmitForm()
    if form.validate_on_submit():
        # Deliver swift justice
        if form.fleg.data == 'V375BrzPaT':
            return snoopin()
        try:
            solved = core.add_fleg(form.fleg.data, team)
        except CtfException as exc:
            flash(exc.message, 'danger')
        else:
            flash('Correct! You have earned {0:d} points for your team.'
                  .format(solved.points), 'success')

        return redirect(url_for('.submit_fleg'), code=303)
    name = core.get_name()
    return render_template('submit.html', name=name, form=form)


@bp.route('/file/<category>/<name>/')
@ensure_team
def get_resource(team, category, name):
    resource = core.get_resource(team, category, name)
    if resource is None:
        abort(404)
    else:
        return send_from_directory(resource.path, resource.name,
                                   as_attachment=True)
