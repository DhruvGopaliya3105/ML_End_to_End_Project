# Doctor Desk — `/doctor-desk`

Ek alag dashboard for the **doctor** role. Same login page, same accounts table —
bas login ke baad DOCTOR role seedha apne desk par land karta hai
(`src/routers/auth.py` → `landing = "/doctor-desk"`), aur dashboard par ek
**Doctor Desk** card bhi hai.

Everything on it is read from the live database on every request: no counter, tag
or amount is stored as text anywhere.

---

## 1. Kya kya add kia (feature list)

### Patient register (`/doctor-desk`)

| Block | What it shows | Source |
|---|---|---|
| 6 tiles | enrolled patients, new this month, visits booked today, overdue follow-ups, total dues, urgent notes | `desk_tiles()` — fresh queries |
| Live search | name / email / phone / `#id`, instant filter of the loaded page + server-side search of the whole register | `list_patients()` |
| Scope chips (with counts) | All patients · My patients · New patients · Follow-up due · Payment due · Urgent notes · No visit 90+ days · Review pending · Never visited | computed from the same aggregates, so the counts always match the list |
| Sort + direction | last visit, first visit, number of visits, amount due, name, their rating | `?sort=&direction=` |
| Row per patient | initials avatar, `SJV-00007` file no, age/gender, email, first visit date, last visit + "N days ago", visit count, consultation notes, Rx count + medicine lines, treatment count, notes count (+urgent), reports, billed / paid / due, medicine orders | `aggregate_stats()` — 8 grouped queries, not 8 × N |
| Auto tags on the file | `NEW`, `Follow-up overdue`, `Payment due`, `Treatment ongoing`, `No visit 90+d`, `No review yet`, `Not your patient` | derived, each with a hover explanation |
| Actions | **Open file** · **Note** · **Statement** | deep links into the file tabs |
| Pagination | 5–100 per page (default 15) | server side |
| JSON | `GET /doctor-desk/api/patients?q=`, `GET /doctor-desk/api/summary` | for the search box / any custom UI |

Aapki "har patient ka access" wali baat ke liye: doctor role ko default me
`doctor.patients.all` milta hai → **sabhi enrolled patients** khulte hain. Ek bhi
permission admin ke Access tab se off karo to list apne-aap "mine only" ho jaati
hai (list + file + statement, teeno block ho jaate hain) — code me koi hard-coded
"doctor can see everything" nahi hai.

### One patient file (`/doctor-desk/patient/{id}`) — 10 tabs

1. **Overview** — aage kya aana hai (next booked visit), next follow-up (with
   *overdue*), ongoing treatment + kis din se chal rahi hai, paisa (billed/paid/
   due/refunded), **allergy + red-flag notes** top par, latest activity timeline,
   quick "add note" form.
2. **Visits & payments** — *kitni baar aaya, pehle kab, kis time*: har appointment
   ki date, start–end time, duration, visit type, doctor + specialization, status,
   reason, cancel hua to kisne/kyun, **fee, method, PAID/PENDING, refund**.
   Right side me ek inline form → desk se hi payment **PAID / PENDING / REFUNDED /
   FAILED / NOT_REQUIRED** mark karo (amount + method ke saath). Yehi
   `appointments.payment_status` update karta hai jo receipt page use karta hai.
3. **Consultation notes** — saare `medical_records` (complaint, symptoms,
   examination, diagnosis, treatment, medicines, advice, status) + **naya record
   likhne ka form** + follow-up schedule karne ka form + "Mark completed".
4. **Prescriptions** — har Rx card: date, doctor, diagnosis, med lines
   (medicine | dose | frequency | duration | advice). Naya Rx yahin se likhte ho:
   ek line = ek dawai, `|` se columns. **"Send to patient's cart"** button us Rx ko
   patient ke pharmacy cart me daal deta hai (jo stock me hai wahi; baaki skip
   kaaran ke saath).
5. **Medicines taken** — *konsi tablet, kitne din li*: per medicine — kitni baar
   prescribe hui, **total days**, courses (expand karke dose/freq/din), kitne
   **packs actually kharide**, kitna **kharcha**, **kahaan se li** (clinic counter /
   delivered home / partner chemist), paid ya nahi, pehli/aakhli date + "N days ago".
   Source = `prescription_medicines` **merge with** `pharmacy_order_items`.
6. **Full invoice** — pura hisaab: upar 6 totals (billed, paid, due, refunded,
   rows, unpaid), neeche ek ledger (appointment fees **aur** medicine orders ek saath,
   date desc, method, transaction reference, refund) + har order ka **item-by-item**
   breakdown (form/strength/pack/qty/dose/din/rate/line total, subtotal+delivery+total,
   address, note, "handed over" time) + **Print / PDF** link.
7. **Doctor notes** — private file notes: type (Note / Advice / Allergy / Red flag /
   Billing / Follow-up / Visit summary), **Pin**, **Urgent**, **Only doctors see
   this** vs **Patient can read it**, optional come-back date. Pin/urgent/archive
   one-click. Archive = soft delete, row delete nahi hoti.
8. **Patient reviews** — unka diya hua feedback: rating stars, comment, outcome,
   current condition, experience, follow-up preference, reason for change, kis
   treatment par.
9. **Reports** — uploaded documents (name, type, KB, date, status) + AI screening
   history (symptoms, severity, suggested specialist, advice).
10. **Timeline** — visits + records + Rx + orders + payments + follow-ups + reviews
    + uploads + screenings + notes = **ek line me**, newest first, colour dots.

Plus: `GET /doctor-desk/patient/{id}/statement` (printable A4 sheet: bill-to,
issued-by, ledger, totals, signature lines — "not a GST invoice" likha hua hai),
`GET .../invoice/{order_no}` (kisi ek medicine order ka print),
`GET .../api/file` (poora file as JSON).

### Privacy jo saath me aayi

* **Har file open `pharmacy_audit_logs` me likha jata hai** (`doctor.patient.view`,
  kaun sa tab dekha). Notes/record/Rx/follow-up/payment sab `doctor.*` actions ke
  saath, before/after values ke saath. Admin → Pharmacy admin → Audit.
* Note ka `visibility`: `PATIENT_VISIBLE` wale notes patient ke apne
  `/medical-history` page par dikh-te hain; `DOCTOR_ONLY` sirf desk par.

---

## 2. Pura workflow (summary)

```
patient signup  ─┐
                 ├─> users (role=PATIENT) ── appointments / medical_records /
doctor login ────┘    prescriptions / follow_ups / treatment_reviews /
                      pharmacy_orders  (pehle se maujood tables)
        │
        ▼
POST /login (email + password)              ← naya: role DOCTOR → 303 /doctor-desk
        │
        ▼
GET /doctor-desk
   guard_page(request, db, "doctor.desk.read")        ← rbac.py
   visible_patient_ids()  ── doctor.patients.all on  → sab patients
                              off → sirf jinke saath uska appointment/record/Rx
   aggregate_stats()  ──► chips, counts, tags, sort, pagination   (sab live SQL)
        │
        ▼  "Open file" (patient id)
GET /doctor-desk/patient/{id}?tab=…
   _open_patient(): guard + scope check + permission check per tab
   desk.dossier()  ──► profile, visits, records, treatments, follow_ups,
                      prescriptions+lines, reviews, reports, screenings,
                      notes, medicine journey, timeline, ledger, orders
   audit: doctor.patient.view
        │
        ├── POST …/notes                       note add  ──► doctor_patient_notes
        ├── POST /notes/{id}/flag              pin / urgent / archive
        ├── POST …/record                      consultation note ──► medical_records
        ├── POST …/follow-up                   ──► follow_ups (patient ko reminder)
        ├── POST …/prescription                ──► prescriptions + prescription_medicines
        │        └── POST /prescription/{id}/send-to-cart
        │                     └──► patient ka cart ──► /pharmacy/cart → checkout
        │                            (patient khud pay karta hai, counter ko order dikhta hai)
        └── POST /appointment/{id}/payment     ──► appointments.payment_* (fee/refund)
                   │
                   ▼
GET …/statement  →  printable sheet (counter par hand over)
```

Round trip jo ab possible hai: **doctor → Rx likha → patient ko /pharmacy/prescriptions
par dikha → cart me push → patient ne cash/UPI se order confirm → counter ne
handed over → patient ke file ke "Medicines taken" + "Full invoice" me turant aa gaya
(kitne packs, kitne din, kahaan se, paid ya nahi)** — aur appointment wali fee bhi
usi ledger me hai, isliye "ek patient ka total kitna bana, kitna diya, kitna baaki"
ek jagah dikhta hai.

---

## 3. Files

| File | Role |
|---|---|
| `src/models/doctor_patient_note.py` | `doctor_patient_notes` table (12th pharmacy-module table) |
| `src/services/doctor_desk_service.py` | saara aggregation + writers (notes, record, Rx, follow-up, payment, cart push, audit) |
| `src/routers/doctor_desk.py` | `/doctor-desk` routes (5 pages + 3 JSON + 9 writes) |
| `templates/doctor_desk.html` | register page |
| `templates/doctor_patient.html` | patient file (10 tabs) |
| `templates/doctor_invoice.html` | statement + single-order invoice (print CSS) |
| `templates/partials/doctor_nav.html` | desk navbar |
| `static/pharmacy.css` | `dd-*` styles appended (pharmacy + desk = one stylesheet) |
| `src/security/rbac.py` | 7 naye permission keys (`doctor.desk.read`, `doctor.record.write`, `doctor.prescribe.write`, `doctor.note.write`, `doctor.billing.read`, `doctor.billing.write`, `doctor.patients.all`) + role defaults |
| `src/models/__init__.py`, `main.py` | model register + `include_router` |
| `src/routers/auth.py` | DOCTOR login → `/doctor-desk` |
| `src/routers/medical_history.py` + `templates/medical_history.html` | `PATIENT_VISIBLE` notes share hote hain |
| `templates/dashboard.html` | Doctor Desk quick card (DOCTOR / ADMIN / SUPERUSER) |
| `seed_pharmacy.py` | demo OPD history + notes (guarded, idempotent) |
| `test_pharmacy.py` §15–17 | the desk checks inside the 173 (pages, 10 tabs, every POST, RBAC) |
| `check_all_features.py` | 319 cross-feature checks - desk links, tabs, orphan rows, the doctor → Rx → cart → order flow |
| `test_pharmacy_mysql.py` | desk checks on MySQL (52 checks) |

**Login kon:** `doctor@demo.com` / `Doctor@1234` (doosre roles: `patient@demo.com` /
`Demo@1234`, `admin@demo.com` / `Admin@1234`, `pharmacist@demo.com` / `Pharma@1234`,
`superuser@sanjeevani.com` / `Super@1234`).

**Doctor row se link kaise:** login `users` me hota hai, appointments `doctors` table
se. Service email match karta hai, phir name match (`Dr. Vikram Joshi`). Agar kisi
login ka koi `doctors` row nahi mila to desk khulta hai (aap "unlinked" banner ke
saath sab patients dekhte ho) par "My patients" filter khali rahega — asli clinic me
doctor ka login email uske `doctors.email` se milna chahiye.

---

## 4. MySQL par naya table

`workbench_pharmacy.sql` ab **12** tables banata hai (27 total with your clinic
tables). Purana file paste kar chuke ho? Bas **dubara paste karke Execute All**
kar do — sab `CREATE TABLE IF NOT EXISTS` hai, data ko kuch nahi hoga; sirf
`doctor_patient_notes` add hoga. Ya app ko chhod do: startup par
`Base.metadata.create_all()` table khula bana deta hai.

`python seed_pharmacy.py` chalao to demo OPD history bhi aa jaati hai
(5 appointments, 3 consultation notes, 1 treatment, 2 follow-ups, 1 review,
3 doctor notes, ek naya patient `sunita@demo.com` / `Demo@1234`) — table me
pehle se us patient ka kuch bhi mila to seed haath nahi lagata.

---

## 5. Jaan bujh ke na kiya gaya

* Patient ka invoice **edit** nahi kar sakte (orders ka refund/cancel sirf
  pharmacy counter / admin) — desk pe fee record karna allowed hai.
* `delete` kahin bhi nahi: notes archive hote hain, records status se close.
* Koi extra dependency nahi (stdlib + jo requirements.txt me pehle se hai).
* GST invoice / barcode / courier tracking / SMS reminders abhi bhi nahi bane.
