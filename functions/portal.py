import os
import json
from flask import Flask, render_template_string, request, redirect, flash
import re  # <-- Missing import added here
from dotenv import load_dotenv
# Import send_whatsapp_text from server.py

# Import send_whatsapp_text from server.py only (no prod_workflow)

load_dotenv(override=True)
# --- WhatsApp Messaging Function (copied from server.py, no import) ---
import requests
PHONE_NUMBER_ID = "719531424575718"
import os
ACCESS_TOKEN = os.getenv("ACESS")
def send_whatsapp_text(to, body):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body}
    }
    res = requests.post(url, headers=headers, json=payload)
    print("📤 Text sent:", res.status_code, res.text)

# Firebase Admin SDK setup (same as web_portal.py)
try:
    import firebase_admin
    from firebase_admin import db
    FIREBASE_DATABASE_URL = "https://diesel-ellipse-463111-a5-default-rtdb.asia-southeast1.firebasedatabase.app/"
    
    firebase_app = None
    root_ref = None

    def get_firebase_app():
        """Initialize Firebase app if not already initialized."""
        global firebase_app
        if firebase_app is None:
            try:
                if not firebase_admin._apps:
                    firebase_app = firebase_admin.initialize_app(options={'databaseURL': FIREBASE_DATABASE_URL})
                else:
                    firebase_app = firebase_admin._apps[0]
            except Exception as e:
                print(f"❌ Firebase connection failed: {e}")
                firebase_app = None
        return firebase_app

    def get_db_ref():
        """Get database reference, initializing Firebase if needed."""
        global root_ref
        if root_ref is None:
            if get_firebase_app() is not None:
                root_ref = db.reference('/')
        return root_ref

except Exception as e:
    print(f"❌ Firebase import failed: {e}")
    def get_firebase_app():
        return None
    def get_db_ref():
        return None


app = Flask(__name__)
app.secret_key = 'aligner-portal-key'  # Needed for flash messages



html_template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Aligner Case Management</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
<div class="container my-5">
    <h1 class="mb-4">Aligner Case Management</h1>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        <div class="mb-3">
          {% for category, message in messages %}
            <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
              {{ message }}
              <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
          {% endfor %}
        </div>
      {% endif %}
    {% endwith %}
    <form method="GET" action="/search">
        <div class="row g-3">
            <div class="col-md-3">
                <input type="text" class="form-control" name="doctor" placeholder="Doctor ID or Number">
            </div>
            <div class="col-md-3">
                <input type="text" class="form-control" name="doctor_name" placeholder="Doctor Name">
            </div>
            <div class="col-md-3">
                <input type="text" class="form-control" name="patient" placeholder="Patient Name">
            </div>
            <div class="col-md-3">
                <input type="text" class="form-control" name="case_id" placeholder="Case ID">
            </div>
        </div>
        <div class="row g-3 mt-2">
            <div class="col-md-3 offset-md-9">
                <button type="submit" class="btn btn-success w-100">Search</button>
            </div>
        </div>
    </form>
    {% if results is defined %}
    <div class="mt-5">
        <h4>Search Results</h4>
        {% if results %}
        <table class="table table-bordered table-hover mt-3">
            <thead class="table-light">
                <tr>
                    <th>Doctor (User ID)</th>
                    <th>Doctor Name</th>
                    <th>Case ID</th>
                    <th>Patient Name</th>
                    <th>Status</th>
                    <th>Update Status</th>
                </tr>
            </thead>
            <tbody>
            {% for r in results %}
                <tr>
                    <td>{{ r.user_id }}</td>
                    <td>{{ r.doctor_name }}</td>
                    <td>{{ r.case_id }}</td>
                    <td>{{ r.patient_name }}</td>
                    <td>
                        {{ r.status or '' }}
                        {% if r.status == 'location_received' and r.delivery_location %}
                            <br><span class="badge bg-info text-dark">Location: {{ r.delivery_location }}</span>
                            <div class="mt-2">
                                <form method="POST" action="/porter_order">
                                    <input type="hidden" name="user_id" value="{{ r.user_id }}">
                                    <input type="hidden" name="case_id" value="{{ r.case_id }}">
                                    <input type="hidden" name="status" value="dispatched">
                                    <div class="mb-1">
                                        <label class="form-label mb-0">Pickup Location (From):</label>
                                        <input type="text" class="form-control form-control-sm mb-1" id="pickup_address_{{ r.case_id }}" placeholder="Type address or coordinates..." autocomplete="off">
                                        <div class="list-group position-absolute w-100" id="pickup_suggestions_{{ r.case_id }}" style="z-index:1000; display:none;"></div>
                                        <input type="text" class="form-control form-control-sm" id="pickup_location_{{ r.case_id }}" name="pickup_location" placeholder="Selected address or coordinates" required readonly style="background:#fff;cursor:pointer;">
                                        <input type="hidden" id="pickup_latlng_{{ r.case_id }}" name="pickup_latlng">
                                    <div id="map_picker_{{ r.case_id }}" style="width:100%;height:250px;"></div>
                                    </div>
                                    <script>
                                    // Leaflet.js Picker with Nominatim Search (OpenStreetMap)
                                    (function() {
                                        var addressInput = document.getElementById('pickup_address_{{ r.case_id }}');
                                        var suggestionsDiv = document.getElementById('pickup_suggestions_{{ r.case_id }}');
                                        var input = document.getElementById('pickup_location_{{ r.case_id }}');
                                        var latlngInput = document.getElementById('pickup_latlng_{{ r.case_id }}');
                                        var mapDiv = document.getElementById('map_picker_{{ r.case_id }}');
                                        var defaultLat = 28.6139, defaultLng = 77.2090;
                                        var lastResults = [];
                                        function showMapAndInit() {
                                            // Remove any previous map instance
                                            if (mapDiv._leaflet_id) {
                                                mapDiv._leaflet_id = null;
                                                mapDiv.innerHTML = "";
                                            }
                                            var map = L.map(mapDiv).setView([defaultLat, defaultLng], 12);
                                            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                                                attribution: '© OpenStreetMap contributors'
                                            }).addTo(map);
                                            var marker = L.marker([defaultLat, defaultLng], {draggable:true}).addTo(map);
                                            function updateLocation(lat, lng, address) {
                                                latlngInput.value = lat + ',' + lng;
                                                input.value = address ? address : (lat + ',' + lng);
                                                addressInput.value = address ? address : (lat + ',' + lng);
                                            }
                                            // Reverse geocode
                                            function reverseGeocode(lat, lng) {
                                                fetch('https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=' + lat + '&lon=' + lng)
                                                    .then(r => r.json())
                                                    .then(data => {
                                                        updateLocation(lat, lng, data.display_name || (lat + ',' + lng));
                                                    })
                                                    .catch(() => updateLocation(lat, lng));
                                            }
                                            // Geocode search with suggestions
                                            addressInput.addEventListener('input', function() {
                                                var q = addressInput.value.trim();
                                                if (q.length < 3) {
                                                    suggestionsDiv.style.display = 'none';
                                                    return;
                                                }
                                                fetch('https://nominatim.openstreetmap.org/search?format=jsonv2&q=' + encodeURIComponent(q))
                                                    .then(r => r.json())
                                                    .then(results => {
                                                        lastResults = results;
                                                        suggestionsDiv.innerHTML = '';
                                                        if (results && results.length > 0) {
                                                            results.slice(0, 5).forEach(function(res, idx) {
                                                                var item = document.createElement('button');
                                                                item.type = 'button';
                                                                item.className = 'list-group-item list-group-item-action';
                                                                item.textContent = res.display_name;
                                                                item.onclick = function() {
                                                                    var lat = parseFloat(res.lat), lng = parseFloat(res.lon);
                                                                    map.setView([lat, lng], 16);
                                                                    marker.setLatLng([lat, lng]);
                                                                    updateLocation(lat, lng, res.display_name);
                                                                    suggestionsDiv.style.display = 'none';
                                                                };
                                                                suggestionsDiv.appendChild(item);
                                                            });
                                                            suggestionsDiv.style.display = 'block';
                                                            // Auto-move pin to first suggestion
                                                            var first = results[0];
                                                            var lat = parseFloat(first.lat), lng = parseFloat(first.lon);
                                                            map.setView([lat, lng], 16);
                                                            marker.setLatLng([lat, lng]);
                                                            updateLocation(lat, lng, first.display_name);
                                                        } else {
                                                            suggestionsDiv.style.display = 'none';
                                                        }
                                                    });
                                            });
                                            // Hide suggestions on blur (with delay for click)
                                            addressInput.addEventListener('blur', function() {
                                                setTimeout(function() { suggestionsDiv.style.display = 'none'; }, 200);
                                            });
                                            // Keyboard navigation (optional, basic)
                                            addressInput.addEventListener('keydown', function(e) {
                                                var items = suggestionsDiv.querySelectorAll('button');
                                                if (!items.length || suggestionsDiv.style.display === 'none') return;
                                                var idx = Array.from(items).findIndex(it => it === document.activeElement);
                                                if (e.key === 'ArrowDown') {
                                                    e.preventDefault();
                                                    if (idx < items.length - 1) items[idx + 1].focus();
                                                    else items[0].focus();
                                                } else if (e.key === 'ArrowUp') {
                                                    e.preventDefault();
                                                    if (idx > 0) items[idx - 1].focus();
                                                    else items[items.length - 1].focus();
                                                } else if (e.key === 'Enter' && idx >= 0) {
                                                    e.preventDefault();
                                                    items[idx].click();
                                                }
                                            });
                                            marker.on('dragend', function(e) {
                                                var latlng = marker.getLatLng();
                                                reverseGeocode(latlng.lat, latlng.lng);
                                            });
                                            map.on('click', function(e) {
                                                marker.setLatLng(e.latlng);
                                                reverseGeocode(e.latlng.lat, e.latlng.lng);
                                            });
                                            // Set initial value
                                            reverseGeocode(defaultLat, defaultLng);
                                        }
                                        // Only initialize map after DOM is ready and visible
                                        if (document.readyState === 'complete' || document.readyState === 'interactive') {
                                            setTimeout(showMapAndInit, 200);
                                        } else {
                                            document.addEventListener('DOMContentLoaded', function() {
                                                setTimeout(showMapAndInit, 200);
                                            });
                                        }
                                    })();
                                    </script>
                                    <button type="submit" class="btn btn-success btn-sm mt-1">Direct Porter</button>
                                </form>
                            </div>
                        {% endif %}
                    </td>
                    <td>

                        {# Scan received UI logic #}
                        {% if r.scan_recieved is defined and r.scan_recieved %}
                            <span class="badge bg-success">&#10003; Scan Received</span>
                        {% else %}
                            <form method="POST" action="/mark_scan_received" style="display:inline;">
                                <input type="hidden" name="user_id" value="{{ r.user_id }}">
                                <input type="hidden" name="case_id" value="{{ r.case_id }}">
                                <button type="submit" class="btn btn-outline-secondary btn-sm">Mark as Received</button>
                            </form>
                            <form method="POST" action="/send_scan_remark" style="display:inline; margin-left:8px;">
                                <input type="hidden" name="user_id" value="{{ r.user_id }}">
                                <input type="hidden" name="case_id" value="{{ r.case_id }}">
                                <input type="hidden" name="patient_name" value="{{ r.patient_name }}">
                                <input type="text" name="scan_remark" class="form-control form-control-sm d-inline-block" style="width:180px;display:inline-block;vertical-align:middle;" placeholder="Write scan comment..." required>
                                <button type="submit" class="btn btn-warning btn-sm" style="vertical-align:middle;">Send Remark</button>
                            </form>
                        {% endif %}


                        <form method="POST" action="/update_status" class="d-flex gap-2 align-items-center flex-wrap">
                            <input type="hidden" name="user_id" value="{{ r.user_id }}">
                            <input type="hidden" name="case_id" value="{{ r.case_id }}">
                            <select class="form-select form-select-sm" name="status" onchange="toggleConsignmentFields(this, this.form)">
                                <option value="ApprovedForProduction" {% if r.status=='ApprovedForProduction' %}selected{% endif %}>Approved for Production</option>
                                <option value="FabricationStarted" {% if r.status=='FabricationStarted' %}selected{% endif %}>Fabrication Started</option>
                                <option value="location_asked" {% if r.status=='location_asked' %}selected{% endif %}>Location Asked</option>
                                <option value="location_received" {% if r.status=='location_received' %}selected{% endif %}>Location Received</option>
                                <option value="dispatched" {% if r.status=='dispatched' %}selected{% endif %}>Dispatched</option>
                                <option value="fit_confirmation" {% if r.status=='fit_confirmation' %}selected{% endif %}>Fit Confirmation</option>
                                <option value="preference_asked" {% if r.status=='preference_asked' %}selected{% endif %}>Preference Asked</option>
                                <option value="fabrication_started" {% if r.status=='fabrication_started' %}selected{% endif %}>Fabrication Started (Preference)</option>
                            </select>
                            <input type="text" class="form-control form-control-sm ms-1" name="consignment_items" placeholder="Consignment Items" style="min-width:120px; display: {% if r.status == 'dispatched' %}inline-block{% else %}none{% endif %};">
                            <input type="text" class="form-control form-control-sm ms-1" name="tracking_id" placeholder="Tracking ID" style="min-width:100px; display: {% if r.status == 'dispatched' %}inline-block{% else %}none{% endif %};">
                            <input type="text" class="form-control form-control-sm ms-1" name="tracking_site" placeholder="Tracking Site" style="min-width:100px; display: {% if r.status == 'dispatched' %}inline-block{% else %}none{% endif %};">
                            <button type="submit" class="btn btn-primary btn-sm">Update</button>
                        </form>
                    </td>
                </tr>
            {% endfor %}
            </tbody>
        </table>
        {% else %}
            <div class="alert alert-warning">No results found.</div>
        {% endif %}
    </div>
    {% endif %}
    <div class="mt-5">
        <h4>Add/Update Case</h4>
        <form method="POST" action="/submit">
            <div class="row g-3">
                <div class="col-md-4">
                    <label for="doctor" class="form-label">Doctor (User ID)</label>
                    <input type="text" class="form-control" id="doctor" name="doctor">
                </div>
                <div class="col-md-4">
                    <label for="patient" class="form-label">Patient Name</label>
                    <input type="text" class="form-control" id="patient" name="patient">
                </div>
                <div class="col-md-4">
                    <label for="case_id" class="form-label">Case ID</label>
                    <input type="text" class="form-control" id="case_id" name="case_id">
                </div>
                <div class="col-md-12">
                    <label for="status" class="form-label">Status</label>
                    <select class="form-select" id="status" name="status">
                        <option value="ApprovedForProduction">Approved for Production</option>
                        <option value="FabricationStarted">Fabrication Started</option>
                        <option value="location_asked">Location Asked</option>
                        <option value="location_received">Location Received</option>
                        <option value="dispatched">Dispatched</option>
                        <option value="fit_confirmation">Fit Confirmation</option>
                        <option value="preference_asked">Preference Asked</option>
                        <option value="fabrication_started">Fabrication Started (Preference)</option>
                    </select>
                </div>
            </div>
            <div class="mt-4">
                <button type="submit" class="btn btn-primary">Submit</button>
            </div>
        </form>
    </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
<script>
function toggleConsignmentFields(select, form) {
    var show = select.value === 'dispatched';
    var items = form.querySelector('input[name="consignment_items"]');
    var tid = form.querySelector('input[name="tracking_id"]');
    var tsite = form.querySelector('input[name="tracking_site"]');
    if (items) items.style.display = show ? 'inline-block' : 'none';
    if (tid) tid.style.display = show ? 'inline-block' : 'none';
    if (tsite) tsite.style.display = show ? 'inline-block' : 'none';
}
// On page load, attach change event to all status selects to ensure correct field visibility
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('select[name="status"]').forEach(function(sel) {
        sel.addEventListener('change', function() { toggleConsignmentFields(this, this.form); });
        // Also trigger once to set initial state
        toggleConsignmentFields(sel, sel.form);
    });
});
</script>
</body>
</html>
'''

# Route to send scan remark to doctor via WhatsApp and update session (backend only)
@app.route('/send_scan_remark', methods=['POST'])
def send_scan_remark():
    user_id = request.form.get('user_id', '').strip()
    case_id = request.form.get('case_id', '').strip()
    patient_name = request.form.get('patient_name', '').strip()
    remark = request.form.get('scan_remark', '').strip()
    if not (user_id and case_id and remark):
        flash('Missing data to send scan remark.', 'danger')
        return redirect(request.referrer or '/')
    root_ref = get_db_ref()
    if root_ref:
        try:
            # Set current_stage and active in Firebase for this doctor
            user_session_ref = root_ref.child('user_sessions').child(user_id)
            user_session_ref.update({
                'current_stage': 'fetch_scan',
                'active': case_id
            })
            # Compose WhatsApp message
            msg = f"Scan Remark for Patient: {patient_name}\nCase ID: {case_id}\nComment: {remark}"
            send_whatsapp_text(user_id, msg)
            flash('Scan remark sent to doctor via WhatsApp.', 'success')
        except Exception as e:
            flash(f'Error sending scan remark: {e}', 'danger')
    else:
        flash('Firebase not connected.', 'danger')
    return redirect(request.referrer or '/')

# Home page (form)
@app.route('/', methods=['GET'])
def index():
    return render_template_string(html_template)

# Search route
@app.route('/search', methods=['GET'])
def search():
    doctor = request.args.get('doctor', '').strip().lower()
    doctor_name = request.args.get('doctor_name', '').strip().lower()
    patient = request.args.get('patient', '').strip().lower()
    case_id = request.args.get('case_id', '').strip().lower()

    results = []
    root_ref = get_db_ref()
    if root_ref:
        try:
            user_sessions = root_ref.child('user_sessions').get() or {}
            for user_id, user_data in user_sessions.items():
                # user_id can be a phone number or doctor name/number
                # user_data is a dict of cases and metadata
                doc_name = user_data.get('name', '') if isinstance(user_data, dict) else ''
                # Doctor ID/number search
                doctor_id_match = not doctor or doctor in user_id.lower()
                # Doctor name search
                doctor_name_match = not doctor_name or doctor_name in doc_name.lower()
                if not (doctor_id_match and doctor_name_match):
                    continue
                for cid, case in user_data.items():
                    # skip non-case keys
                    if not isinstance(case, dict) or 'name' not in case:
                        continue
                    # Patient search
                    patient_match = not patient or patient in case.get('name','').lower()
                    # Case ID search
                    caseid_match = not case_id or case_id in cid.lower()
                    if patient_match and caseid_match:
                        results.append({
                            'user_id': user_id,
                            'doctor_name': doc_name,
                            'case_id': cid,
                            'patient_name': case.get('name',''),
                            'status': case.get('status',''),
                            'delivery_location': case.get('delivery_location', ''),
                            'scan_recieved': case.get('scan_recieved', False)
                        })
        except Exception as e:
            flash(f"Firebase error: {e}", 'danger')
    else:
        flash('Firebase not connected.', 'danger')
    return render_template_string(html_template, results=results)


# Handle form submission and update Firebase
@app.route('/submit', methods=['POST'])
def submit():
    doctor = request.form.get('doctor', '').strip()
    patient = request.form.get('patient', '').strip()
    case_id = request.form.get('case_id', '').strip()
    status = request.form.get('status', '').strip()

    if not (doctor and patient and case_id and status):
        flash('All fields are required.', 'danger')
        return redirect('/')

    user_id = doctor

    root_ref = get_db_ref()
    if root_ref:
        try:
            case_ref = root_ref.child('user_sessions').child(user_id).child(case_id)
            case_data = case_ref.get() or {}
            case_data['status'] = status
            case_data['name'] = patient
            case_ref.update(case_data)
            flash(f"Status for case {case_id} updated to '{status}' in Firebase.", 'success')
        except Exception as e:
            flash(f"Firebase error: {e}", 'danger')
    else:
        flash('Firebase not connected.', 'danger')
    return redirect('/')

# Update status from search table
@app.route('/update_status', methods=['POST'])
def update_status():
    user_id = request.form.get('user_id', '').strip()
    case_id = request.form.get('case_id', '').strip()
    status = request.form.get('status', '').strip()
    if not (user_id and case_id and status):
        flash('Missing data for update.', 'danger')
        return redirect('/')
    root_ref = get_db_ref()
    if root_ref:
        try:
            case_ref = root_ref.child('user_sessions').child(user_id).child(case_id)
            case_data = case_ref.get() or {}
            case_data['status'] = status
            case_ref.update(case_data)
            flash(f"Status for case {case_id} updated to '{status}' in Firebase.", 'success')
            # Send WhatsApp message to doctor (user_id)
            # Compose message as in server.py logic
            patient_name = case_data.get('name', '')
            msg = None
            if status == 'ApprovedForProduction':
                msg = f"We have started production for your case.\nPatient Name: {patient_name}\nYou will receive updates as your case progresses."
            elif status == 'FabricationStarted':
                msg = f"This is to inform you that the process of Aligner Fabrication has been initiated.\nPatient Name: {patient_name}\nDispatch details will soon be provided to you."
            elif status == 'location_asked':
                msg = f"Please provide a valid location coordinates using location icon for the delivery location.\nPatient Name: {patient_name}"
            elif status == 'location_received':
                msg = f"Thank you for providing the delivery location.\nPatient Name: {patient_name}\nWe will dispatch your aligners to this address -> {case_data.get('delivery_location', 'Not specified')}"
            elif status == 'dispatched':
                # Only in dispatched, update consignment info if provided
                consignment_items = request.form.get('consignment_items', '').strip()
                tracking_id = request.form.get('tracking_id', '').strip()
                tracking_site = request.form.get('tracking_site', '').strip()
                update_fields = {}
                if consignment_items:
                    update_fields['consignment_items'] = consignment_items
                if tracking_id:
                    update_fields['tracking_id'] = tracking_id
                if tracking_site:
                    update_fields['tracking_site'] = tracking_site
                if update_fields:
                    try:
                        case_ref.update(update_fields)
                        flash('Consignment details updated in Firebase.', 'success')
                    except Exception as e:
                        flash(f'Error updating consignment details: {e}', 'danger')
                msg = f"Thank you for your valuable support.\n\nPlease take a note of details of your shipment :- \nPatient Name: {patient_name}\nConsignment Items: {case_data.get('consignment_items', 'Not specified')}\nTracking ID: {case_data.get('tracking_id', 'Not specified')}\nTracking Site: {case_data.get('tracking_site', 'Not specified')}\n\nIn case if shipment is not delivered to you within 2-4 days of dispatch than please revert back to us. "
            elif status == 'dispatched':
                msg = f"Thank you for your valuable support.\n\nPlease take a note of details of your shipment :- \nPatient Name: {patient_name}\nConsignment Items: {case_data.get('consignment_items', 'Not specified')}\nTracking ID: {case_data.get('tracking_id', 'Not specified')}\nTracking Site: {case_data.get('tracking_site', 'Not specified')}\n\nIn case if shipment is not delivered to you within 2-4 days of dispatch than please revert back to us. "
            elif status == 'fit_confirmation':
                msg = f"We would like to know the fit of training aligner sent to you.\nPatient Name: {patient_name}\nAlso please let us know whether we should go ahead for the fabrication of remaining sets of aligner?\n\nPlease Note: Remaining sets of aligner will be dispatched within a week upon confirmation received for the case."
            elif status == 'preference_asked':
                msg = f"Please specify if you want to proceed with 'full dispatch' or 'phase dispatch' fabrication for the remaining aligners.\nPatient Name: {patient_name}"
            elif status == 'fabrication_started':
                msg = f"This is to inform you that the process of Aligner Fabrication has been initiated.\nPatient Name: {patient_name}"
            elif status == 'unknown':
                msg = f"Your case for {patient_name} is still under processing. We will inform you once it is done. Thank you for using 3D-Align services. Have a great day!"
            if msg:
                # For all workflow after fabrication started, set active case and current_stage
                if status in [
                    'location_asked','fit_confirmation', 'preference_asked'
                ]:
                    try:
                        user_session_ref = root_ref.child('user_sessions').child(user_id)
                        user_session_ref.update({
                            'active': case_id,
                            'current_stage': 'case_tracking'
                        })
                    except Exception as e:
                        flash(f"Error updating active case/current_stage: {e}", 'warning')
                try:
                    send_whatsapp_text(user_id, msg)
                except Exception as e:
                    flash(f"WhatsApp message error: {e}", 'warning')
        except Exception as e:
            flash(f"Firebase error: {e}", 'danger')
    else:
        flash('Firebase not connected.', 'danger')
    # Redirect back to search with previous filters if possible
    return redirect(request.referrer or '/')

# --- Porter API Integration (Real) ---
def place_porter_order(pickup_location, drop_location, patient_name, case_id, pickup_latlng=None, drop_latlng=None, pickup_contact=None, drop_contact=None, pickup_address_details=None, drop_address_details=None):
    """
    Place a real order with Porter API using the new structure.
    All required fields must be provided.
    """
    import requests
    import os
    import uuid
    PORTER_API_KEY = os.getenv('PORTER_API_KEY')
    if not PORTER_API_KEY:
        raise Exception('PORTER_API_KEY not set in environment')
    url = 'https://pfe-apigw-uat.porter.in/v1/orders/create'
    headers = {
        'x-api-key': PORTER_API_KEY,
        'Content-Type': 'application/json'
    }
    # Validate required fields
    if not (pickup_address_details and drop_address_details):
        raise Exception('Pickup and drop address details are required')
    if not (pickup_latlng and drop_latlng):
        raise Exception('Pickup and drop coordinates are required')
    if not (pickup_contact and drop_contact):
        raise Exception('Pickup and drop contact details are required')
    # Build payload
    payload = {
        "request_id": f"PORTAL_{case_id}_{str(uuid.uuid4())[:8]}",
        "delivery_instructions": {
            "instructions_list": [
                {
                    "type": "text",
                    "description": "handle with care"
                }
            ]
        },
        "pickup_details": {
            "address": {
                **pickup_address_details,
                "lat": float(pickup_latlng[0]),
                "lng": float(pickup_latlng[1]),
                "contact_details": pickup_contact
            }
        },
        "drop_details": {
            "address": {
                **drop_address_details,
                "lat": float(drop_latlng[0]),
                "lng": float(drop_latlng[1]),
                "contact_details": drop_contact
            }
        },
        "additional_comments": f"Aligners for {patient_name} (Case {case_id})"
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        tracking_id = data.get('order_id', 'N/A');
        tracking_site = data.get('tracking_url', f'https://porter.in/track/{tracking_id}');
        return {
            'consignment_items': f'Aligners for {patient_name} (Case {case_id})',
            'tracking_id': tracking_id,
            'tracking_site': tracking_site
        }
    except Exception as e:
        raise Exception(f'Porter API error: {e}')

# Route to handle Porter order placement
@app.route('/porter_order', methods=['POST'])
def porter_order():
    user_id = request.form.get('user_id', '').strip()
    case_id = request.form.get('case_id', '').strip()
    status = request.form.get('status', '').strip()
    pickup_location = request.form.get('pickup_location', '').strip()
    pickup_latlng = request.form.get('pickup_latlng', '').strip()
    # For now, ask for pickup contact and address details via form or use defaults
    pickup_contact = {
        "name": "Pickup Contact",
        "phone_number": "+919999999999"
    }
    # Parse pickup lat/lng
    if pickup_latlng:
        try:
            pickup_lat, pickup_lng = [float(x) for x in pickup_latlng.split(",")]
        except Exception:
            flash('Invalid pickup coordinates.', 'danger')
            return redirect(request.referrer or '/')
    else:
        flash('Pickup coordinates required.', 'danger')
        return redirect(request.referrer or '/')
    # Reverse geocode pickup for full address
    pickup_addr_json = reverse_geocode(pickup_lat, pickup_lng)
    if not pickup_addr_json or 'address' not in pickup_addr_json:
        flash('Could not reverse geocode pickup location.', 'danger')
        return redirect(request.referrer or '/')
    pickup_address_details = {
        "apartment_address": pickup_addr_json['address'].get('house_number', ''),
        "street_address1": pickup_addr_json['address'].get('road', pickup_location),
        "street_address2": pickup_addr_json['address'].get('suburb', ''),
        "landmark": pickup_addr_json['address'].get('neighbourhood', ''),
        "city": pickup_addr_json['address'].get('city', pickup_addr_json['address'].get('town', '')),
        "state": pickup_addr_json['address'].get('state', ''),
        "pincode": pickup_addr_json['address'].get('postcode', ''),
        "country": pickup_addr_json['address'].get('country', 'India')
    }
    root_ref = get_db_ref()
    if root_ref:
        try:
            case_ref = root_ref.child('user_sessions').child(user_id).child(case_id)
            case_data = case_ref.get() or {}
            drop_location = case_data.get('delivery_location', '')
            drop_latlng = case_data.get('delivery_latlng', '')
            patient_name = case_data.get('name', '')
            # If drop_location is a URL, extract lat/lng
            drop_lat, drop_lng = None, None
            if drop_location and (drop_location.startswith('http://') or drop_location.startswith('https://')):
                latlng = extract_latlng_from_url(drop_location)
                if latlng:
                    drop_lat, drop_lng = latlng
                    drop_latlng = f"{drop_lat},{drop_lng}"
            elif drop_latlng:
                try:
                    drop_lat, drop_lng = [float(x) for x in drop_latlng.split(",")]
                except Exception:
                    flash('Invalid drop coordinates in Firebase.', 'danger')
                    return redirect(request.referrer or '/')
            if not (drop_lat and drop_lng):
                flash('Drop coordinates missing or invalid. Please update delivery location.', 'danger')
                return redirect(request.referrer or '/')
            # Reverse geocode drop for full address
            drop_addr_json = reverse_geocode(drop_lat, drop_lng)
            if not drop_addr_json or 'address' not in drop_addr_json:
                flash('Could not reverse geocode drop location.', 'danger')
                return redirect(request.referrer or '/')
            drop_contact = {
                "name": patient_name or "Drop Contact",
                "phone_number": user_id if user_id.startswith('+') else "+91" + user_id
            }
            drop_address_details = {
                "apartment_address": drop_addr_json['address'].get('house_number', ''),
                "street_address1": drop_addr_json['address'].get('road', ''),
                "street_address2": drop_addr_json['address'].get('suburb', ''),
                "landmark": drop_addr_json['address'].get('neighbourhood', ''),
                "city": drop_addr_json['address'].get('city', drop_addr_json['address'].get('town', '')),
                "state": drop_addr_json['address'].get('state', ''),
                "pincode": drop_addr_json['address'].get('postcode', ''),
                "country": drop_addr_json['address'].get('country', 'India')
            }
            # Call Porter API (real)
            porter_result = place_porter_order(
                pickup_location, drop_location, patient_name, case_id,
                pickup_latlng=(pickup_lat, pickup_lng),
                drop_latlng=(drop_lat, drop_lng),
                pickup_contact=pickup_contact,
                drop_contact=drop_contact,
                pickup_address_details=pickup_address_details,
                drop_address_details=drop_address_details
            )
            # Update Firebase with returned consignment/tracking info
            update_fields = {
                'status': status,
                'consignment_items': porter_result['consignment_items'],
                'tracking_id': porter_result['tracking_id'],
                'tracking_site': porter_result['tracking_site']
            }
            case_ref.update(update_fields)
            flash('Porter order placed and tracking info updated.', 'success')
            # Send WhatsApp message to doctor
            msg = f"Porter order placed for patient {patient_name}.\nPickup: {pickup_location}\nDrop: {drop_location}\nTracking ID: {porter_result['tracking_id']}\nTrack here: {porter_result['tracking_site']}"
            try:
                send_whatsapp_text(user_id, msg)
            except Exception as e:
                flash(f"WhatsApp message error: {e}", 'warning')
        except Exception as e:
            flash(f"Porter order error: {e}", 'danger')
    else:
        flash('Firebase not connected.', 'danger')
    return redirect(request.referrer or '/')

def extract_latlng_from_url(url):
    # Try to extract lat/lng from Google Maps or OSM URL
    # Google Maps: .../@12.935025,77.609260...
    m = re.search(r'@([\d.\-]+),([\d.\-]+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))
    # OSM: ...?mlat=12.935025&mlon=77.609260...
    m = re.search(r'mlat=([\d.\-]+)&mlon=([\d.\-]+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))
    # Google Maps share link: .../place/.../12.935025,77.609260
    m = re.search(r'/(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None

def reverse_geocode(lat, lng):
    import requests
    url = f'https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lng}'
    try:
        r = requests.get(url, headers={'User-Agent': '3d-align-portal'}, timeout=5)
        if r.status_code == 200:
            return r.json()
    except requests.exceptions.Timeout:
        print('Nominatim reverse geocode timed out')
    except Exception as e:
        print(f'Nominatim reverse geocode error: {e}')
    return None

@app.route('/mark_scan_received', methods=['POST'])
def mark_scan_received():
    user_id = request.form.get('user_id', '').strip()
    case_id = request.form.get('case_id', '').strip()
    if not (user_id and case_id):
        flash('Missing data to mark scan as received.', 'danger')
        return redirect(request.referrer or '/')
    root_ref = get_db_ref()
    if root_ref:
        try:
            case_ref = root_ref.child('user_sessions').child(user_id).child(case_id)
            case_ref.update({'scan_recieved': True})
            flash('Scan marked as received.', 'success')
        except Exception as e:
            flash(f'Error updating scan_recieved: {e}', 'danger')
    else:
        flash('Firebase not connected.', 'danger')
    return redirect(request.referrer or '/')

if __name__ == '__main__':
    app.run(debug=True, port=5001)
