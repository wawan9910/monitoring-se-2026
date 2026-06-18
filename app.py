import os
import json
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'monitoring-se-2026-secret')

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///monitoring.db')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class BlokSensus(db.Model):
    __tablename__ = 'blok_sensus'
    id = db.Column(db.Integer, primary_key=True)
    idsubsls = db.Column(db.String(30))
    nmsls = db.Column(db.String(200))
    kecamatan = db.Column(db.String(100))
    desa = db.Column(db.String(100))
    rt = db.Column(db.Integer, default=0)
    pcl = db.Column(db.String(200))
    pml = db.Column(db.String(200))
    status = db.Column(db.String(50), default='Belum Cacah')
    catatan = db.Column(db.Text, default='')

    STATUS_OPTIONS = ['Sudah Submit', 'Sudah Cacah Belum Submit', 'Belum Cacah', 'Tidak Ada RT']

    def to_dict(self):
        return {
            'id': self.id,
            'idsubsls': self.idsubsls,
            'nmsls': self.nmsls,
            'kecamatan': self.kecamatan,
            'desa': self.desa,
            'rt': self.rt,
            'pcl': self.pcl,
            'pml': self.pml,
            'status': self.status,
            'catatan': self.catatan,
        }


def load_excel_data():
    seed_path = os.path.join(os.path.dirname(__file__), 'seed_data.json')
    if not os.path.exists(seed_path):
        return

    with open(seed_path, encoding='utf-8') as f:
        records = json.load(f)

    for r in records:
        bs = BlokSensus(
            idsubsls=r['idsubsls'],
            nmsls=r['nmsls'],
            kecamatan=r['kecamatan'],
            desa=r['desa'],
            rt=r['rt'],
            pcl=r['pcl'],
            pml=r['pml'],
            status=r['status'],
            catatan=r.get('catatan', ''),
        )
        db.session.add(bs)

    db.session.commit()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/data')
def api_data():
    kec = request.args.get('kec', '')
    desa = request.args.get('desa', '')
    status = request.args.get('status', '')
    search = request.args.get('q', '')

    q = BlokSensus.query
    if kec:
        q = q.filter(BlokSensus.kecamatan == kec)
    if desa:
        q = q.filter(BlokSensus.desa == desa)
    if status:
        q = q.filter(BlokSensus.status == status)
    if search:
        q = q.filter(
            db.or_(
                BlokSensus.pcl.ilike(f'%{search}%'),
                BlokSensus.desa.ilike(f'%{search}%'),
                BlokSensus.nmsls.ilike(f'%{search}%'),
            )
        )

    records = q.all()
    return jsonify([r.to_dict() for r in records])


@app.route('/api/summary')
def api_summary():
    rows = db.session.query(
        BlokSensus.status, func.count(BlokSensus.id)
    ).group_by(BlokSensus.status).all()
    return jsonify({s: c for s, c in rows})


@app.route('/api/kecamatan')
def api_kecamatan():
    kec_list = db.session.query(BlokSensus.kecamatan).distinct().order_by(BlokSensus.kecamatan).all()
    return jsonify([k[0] for k in kec_list])


@app.route('/api/desa')
def api_desa():
    kec = request.args.get('kec', '')
    q = db.session.query(BlokSensus.desa).distinct().order_by(BlokSensus.desa)
    if kec:
        q = q.filter(BlokSensus.kecamatan == kec)
    return jsonify([d[0] for d in q.all()])


@app.route('/api/chart-data')
def api_chart_data():
    rows = db.session.query(
        BlokSensus.kecamatan,
        BlokSensus.status,
        func.count(BlokSensus.id),
        func.sum(BlokSensus.rt)
    ).group_by(BlokSensus.kecamatan, BlokSensus.status).all()

    kec_map = {}
    for kec, status, cnt, rt_sum in rows:
        if kec not in kec_map:
            kec_map[kec] = {}
        kec_map[kec][status] = {'count': cnt, 'rt': int(rt_sum or 0)}

    return jsonify(kec_map)


# ADMIN ROUTES
@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    error = ''
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin'))
        error = 'Password salah!'
    return render_template('login.html', error=error)


@app.route('/admin/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/admin')
@login_required
def admin():
    return render_template('admin.html')


@app.route('/admin/update', methods=['POST'])
@login_required
def update_record():
    data = request.get_json()
    record_id = data.get('id')
    bs = BlokSensus.query.get(record_id)
    if not bs:
        return jsonify({'error': 'Not found'}), 404

    if 'status' in data:
        bs.status = data['status']
    if 'catatan' in data:
        bs.catatan = data['catatan']
    if 'pcl' in data:
        bs.pcl = data['pcl']
    if 'pml' in data:
        bs.pml = data['pml']
    if 'rt' in data:
        bs.rt = int(data['rt'])

    db.session.commit()
    return jsonify({'ok': True, 'record': bs.to_dict()})


@app.route('/admin/bulk-update', methods=['POST'])
@login_required
def bulk_update():
    data = request.get_json()
    ids = data.get('ids', [])
    status = data.get('status')
    if not ids or not status:
        return jsonify({'error': 'Missing data'}), 400

    BlokSensus.query.filter(BlokSensus.id.in_(ids)).update(
        {'status': status}, synchronize_session=False
    )
    db.session.commit()
    return jsonify({'ok': True, 'updated': len(ids)})


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if BlokSensus.query.count() == 0:
            load_excel_data()
    app.run(debug=True, port=5001)
