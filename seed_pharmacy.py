"""Fill the pharmacy: diseases, ~65 medicines (price + photo + stock), the
partner chemist shops the emergency search reads from SQL, demo logins for
every role, and one sample prescription so the "Doctor prescribed" tab has
something to buy today.

Works on BOTH databases - your MySQL from .env, or the SQLite fallback -
because it uses the app's own engine and models. It is idempotent: run it
twice and nothing is duplicated (rows are matched by SKU, email, shop name).

    python seed_pharmacy.py            # add whatever is missing
    python seed_pharmacy.py --reset    # wipe pharmacy rows first (users and
                                       # doctors are kept)

Logins (passwords hashed with the app's own Argon2, so they work in /login):

    superuser@sanjeevani.com  Super@1234   SUPERUSER   - everything
    admin@demo.com            Admin@1234   ADMIN       - all but role editing
    pharmacist@demo.com       Pharma@1234  PHARMACIST  - orders, stock, nearby
    doctor@demo.com           Doctor@1234  DOCTOR      - view catalog
    patient@demo.com          Demo@1234    PATIENT     - shop + buy

Run it after the app has started once (it creates the tables itself if they
are not there yet, so running it first is also fine).
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("USE_SQLITE", os.getenv("USE_SQLITE", "false"))
os.environ.setdefault("GROQ_API_KEY", os.getenv("GROQ_API_KEY", "seed-script"))

from src.config import STATIC_DIR  # noqa: E402


# ============================================================
# DEMO LOGINS
# ============================================================

DEMO_USERS = [
    ("Super User", "superuser@sanjeevani.com", "9876500100", "Super@1234", "SUPERUSER"),
    ("Clinic Admin", "admin@demo.com", "9876500200", "Admin@1234", "ADMIN"),
    ("Ravi Pharmacist", "pharmacist@demo.com", "9876500300", "Pharma@1234", "PHARMACIST"),
    ("Dr. Vikram Joshi", "doctor@demo.com", "9876500400", "Doctor@1234", "DOCTOR"),
    ("Demo Patient", "patient@demo.com", "9876543210", "Demo@1234", "PATIENT"),
]


# A pharmacy prescription needs a doctor row. seed_sqlite_demo.py normally
# creates 20 of them; if the database is brand new (only this script ran) we
# add these three so the "Doctor prescribed" tab has real data.
DEMO_DOCTORS = [
    ("Dr. Vikram Joshi", "vikram.joshi@sanjeevani.com", "9876500010", "General Medicine", "MBBS, MD Medicine", 10, 500.00),
    ("Dr. Amit Sharma", "amit.sharma@sanjeevani.com", "9876543210", "Cardiology", "MBBS, MD Cardiology", 8, 800.00),
    ("Dr. Priya Mehta", "priya.mehta@sanjeevani.com", "9876500002", "Dermatology", "MBBS, MD Dermatology", 7, 600.00),
]


# ============================================================
# DISEASES / CATEGORIES   (slug, name, group, icon)
# ============================================================

DISEASES = [
    ("fever", "Fever", "Everyday care", "\U0001F321"),
    ("headache", "Headache & Migraine", "Everyday care", "\U0001F9E4"),
    ("cough-cold", "Cough, Cold & Throat", "Everyday care", "\U0001F927"),
    ("allergy", "Allergy & Skin", "Everyday care", "\U0001F41D"),
    ("acidity", "Acidity & Gas", "Stomach", "\U0001FAE2"),
    ("diarrhoea", "Diarrhoea & Vomiting", "Stomach", "\U0001F922"),
    ("constipation", "Constipation", "Stomach", "\U0001FAD6"),
    ("worms", "Worms & Deworming", "Stomach", "\U0001FAB1"),
    ("pain", "Body Pain & Injury", "Pain", "\U0001F9B4"),
    ("arthritis", "Joint Pain & Arthritis", "Pain", "\U0001F9B6"),
    ("diabetes", "Diabetes", "Chronic", "\U0001F4A0"),
    ("hypertension", "Blood Pressure", "Chronic", "\u2764"),
    ("cholesterol", "Cholesterol", "Chronic", "\U0001F9C8"),
    ("thyroid", "Thyroid", "Chronic", "\U0001F9E0"),
    ("asthma", "Asthma & Breathing", "Chronic", "\U0001FAC1"),
    ("heart", "Heart Care", "Chronic", "\U0001F493"),
    ("kidney", "Kidney & Urine", "Chronic", "\U0001F4A7"),
    ("liver", "Liver Care", "Chronic", "\U0001F9DF"),
    ("antibiotic", "Infections (Antibiotics)", "Prescription only", "\U0001F48A"),
    ("tb", "TB & Long Treatments", "Prescription only", "\U0001FA79"),
    ("anxiety", "Sleep, Stress & Anxiety", "Nervous system", "\U0001F634"),
    ("nerve", "Nerve Pain & Weakness", "Nervous system", "\u26A1"),
    ("eye", "Eye & Ear Care", "Specialist", "\U0001F441"),
    ("dental", "Dental Care", "Specialist", "\U0001F9B7"),
    ("anemia", "Blood & Anemia", "Wellness", "\U0001FA78"),
    ("vitamins", "Vitamins & Supplements", "Wellness", "\U0001F34A"),
    ("immunity", "Immunity & Recovery", "Wellness", "\U0001F6E1"),
    ("womens", "Women's Health", "Wellness", "\U0001F45A"),
    ("child", "Child Care", "Wellness", "\U0001F476"),
    ("first-aid", "First Aid & Wound Care", "At home", "\U0001FA79"),
    ("hygiene", "Hygiene & Sanitizers", "At home", "\U0001F9F4"),
    ("piles", "Piles & Fissure", "At home", "\U0001FAE7"),
]


# ============================================================
# MEDICINES
# (name, generic, brand, form, strength, pack, price, mrp, stock,
#  rx_only, disease tags, how to take)
# ============================================================

MEDICINES = [
    # ---- Fever & general pain ----
    ("Dolo 650 Tablet", "Paracetamol 650 mg", "Micro Labs", "TABLET", "650 mg", "Strip of 15 tablets", 32.00, 35.00, 240, 0, "fever,headache", "After food. Max 4 doses in 24 hours."),
    ("Crocin Advance Tablet", "Paracetamol 500 mg", "GSK", "TABLET", "500 mg", "Strip of 15 tablets", 28.00, 31.50, 180, 0, "fever,headache", "After food."),
    ("Saridon Tablet", "Paracetamol + Ibuprofen + Caffeine", "Bayer", "TABLET", "400/200/32.5 mg", "Strip of 10 tablets", 48.00, 52.00, 90, 0, "fever,headache,pain", "Not on an empty stomach."),
    ("Ibugesic Plus Tablet", "Ibuprofen 400 mg + Paracetamol 325 mg", "FDC", "TABLET", "400/325 mg", "Strip of 15 tablets", 42.00, 46.00, 120, 0, "fever,pain", ""),
    ("Combiflam Tablet", "Ibuprofen 400 mg + Paracetamol 325 mg", "Sanofi", "TABLET", "400/325 mg", "Strip of 20 tablets", 49.00, 55.00, 110, 0, "pain,fever", ""),
    ("Zerodol MR Tablet", "Aceclofenac + Paracetamol + Chloroxazone", "IPCA", "TABLET", "200/325/250 mg", "Strip of 10 tablets", 78.00, 85.00, 60, 1, "pain,arthritis", "Muscle spasm relief. Doctor advised."),
    ("Voveran Tablet", "Diclofenac Sodium 50 mg", "Novartis", "TABLET", "50 mg", "Strip of 20 tablets", 55.00, 61.00, 70, 1, "pain,arthritis", ""),
    ("Brufen Syrup 100ml", "Ibuprofen 100 mg/5 ml", "Abbott", "SYRUP", "100 mg/5 ml", "100 ml bottle", 78.00, 84.00, 45, 0, "fever,child", "Shake well, use the measuring cap."),
    ("Calpol 120 Syrup 60ml", "Paracetamol 120 mg/5 ml", "GSK", "SYRUP", "120 mg/5 ml", "60 ml bottle", 45.00, 49.00, 95, 0, "fever,child", "As per child's weight."),
    ("Ponstan Forte Tablet", "Mefenamic Acid 500 mg", "Pfizer", "TABLET", "500 mg", "Strip of 10 tablets", 58.00, 64.00, 66, 1, "pain,fever", ""),

    # ---- Headache / migraine / sprain ----
    ("Suminat Tablet", "Sumatriptan 50 mg", "Cipla", "TABLET", "50 mg", "Strip of 4 tablets", 120.00, 132.00, 30, 1, "headache", "At the first sign of a migraine."),
    ("Migrabron Tablet", "Ergotamine + Caffeine + Prochlorperazine", "Arbor", "TABLET", "-", "Strip of 10 tablets", 96.00, 105.00, 40, 1, "headache", ""),
    ("Volini Spray 100gm", "Diclofenac Diethylamine 1%", "Sun Pharma", "SPRAY", "1% w/w", "100 gm spray", 195.00, 215.00, 55, 0, "pain", "External use only."),
    ("Moov Cream 20gm", "Topical analgesic", "Reckitt", "CREAM", "-", "20 gm tube", 65.00, 70.00, 130, 0, "pain", "External use only."),
    ("Flexon Injection", "Diclofenac + Paracetamol", "Aristo", "INJECTION", "1 ml", "Ampoule", 42.00, 46.00, 25, 1, "pain,fever", "Nurse / doctor administers."),

    # ---- Cough, cold, throat, allergy ----
    ("Benadryl Cough Syrup 100ml", "Diphenhydramine + Ammonium Chloride", "Johnson", "SYRUP", "-", "100 ml bottle", 118.00, 128.00, 80, 0, "cough-cold", ""),
    ("Ascoril LS Syrup 100ml", "Ambroxol + Levosalbutamol + Guaifenesin", "Glenmark", "SYRUP", "-", "100 ml bottle", 122.00, 134.00, 60, 1, "cough-cold,asthma", ""),
    ("Cetzine Tablet", "Cetirizine 10 mg", "Dr Reddy's", "TABLET", "10 mg", "Strip of 10 tablets", 22.00, 26.00, 200, 0, "cough-cold,allergy", "May cause drowsiness."),
    ("Allegra 120 Tablet", "Fexofenadine 120 mg", "Sanofi", "TABLET", "120 mg", "Strip of 10 tablets", 168.00, 185.00, 90, 0, "allergy,cough-cold", ""),
    ("Sinarest Tablet", "Paracetamol + Phenylephrine + Chlorpheniramine", "Centaur", "TABLET", "-", "Strip of 10 tablets", 62.00, 68.00, 130, 0, "cough-cold,fever", ""),
    ("Chlorpheniramine Tablet", "Chlorpheniramine Maleate 4 mg", "Zuventus", "TABLET", "4 mg", "Strip of 10 tablets", 18.00, 21.00, 150, 0, "cough-cold,allergy", ""),
    ("Strepsils Lozenges", "Amylmetacresol + Dichlorobenzyl Alcohol", "Reckitt", "LOZENGE", "-", "Pack of 16", 99.00, 110.00, 140, 0, "cough-cold", ""),
    ("Otrivin Nasal Spray", "Xylometazoline 0.1%", "GSK", "SPRAY", "0.1%", "10 ml spray", 118.00, 129.00, 70, 0, "cough-cold", "Not more than 5 days."),
    ("Montek LC Tablet", "Montelukast + Levocetirizine", "Sun Pharma", "TABLET", "10/5 mg", "Strip of 10 tablets", 178.00, 196.00, 75, 1, "allergy,asthma", "At bedtime."),
    ("Deriphyllin Tablet", "Etofylline + Theophylline", "Merck", "TABLET", "-", "Strip of 20 tablets", 44.00, 48.00, 55, 1, "asthma,cough-cold", ""),
    ("Asthalin Inhaler", "Salbutamol 100 mcg", "Cipla", "DEVICE", "100 mcg/puff", "200 dose inhaler", 128.00, 141.00, 0, 1, "asthma", "Reliever inhaler. Keep one in your bag."),

    # ---- Acidity ----
    ("Pan 40 Tablet", "Pantoprazole 40 mg", "Alkem", "TABLET", "40 mg", "Strip of 15 tablets", 132.00, 148.00, 160, 1, "acidity", "30 minutes before breakfast."),
    ("Nexpro RD 40 Capsule", "Esomeprazole 40 mg + Domperidone 30 mg", "German Remedies", "CAPSULE", "40/30 mg", "Strip of 10 capsules", 138.00, 152.00, 85, 1, "acidity", ""),
    ("Gelusil MPS Suspension 100ml", "Magaldrate + Simethicone", "Intas", "SUSPENSION", "-", "100 ml bottle", 95.00, 105.00, 110, 0, "acidity", ""),
    ("Digene Gel 150ml", "Magnesium + Aluminium + Simethicone", "Abbott", "GEL", "-", "150 ml bottle", 130.00, 142.00, 65, 0, "acidity", ""),
    ("Omez Capsule 20mg", "Omeprazole 20 mg", "Dr Reddy's", "CAPSULE", "20 mg", "Strip of 20 capsules", 88.00, 98.00, 120, 1, "acidity", ""),
    ("Rantac 150 Tablet", "Ranitidine 150 mg", "JB Chemicals", "TABLET", "150 mg", "Strip of 20 tablets", 38.00, 42.00, 90, 1, "acidity", ""),

    # ---- Diarrhoea, vomiting, worms ----
    ("ORS Orange Sachet", "Oral Rehydration Salts (WHO)", "Electral", "POWDER", "-", "Sachet 21 gm", 22.00, 25.00, 300, 0, "diarrhoea", "Mix in 1 litre of clean water."),
    ("Electral Powder Sachet", "Oral Rehydration Salts", "FDC", "POWDER", "-", "Sachet 21.8 gm", 20.00, 22.00, 260, 0, "diarrhoea,first-aid", ""),
    ("Imodium Capsule", "Loperamide 2 mg", "Janssen", "CAPSULE", "2 mg", "Strip of 10 capsules", 68.00, 75.00, 70, 1, "diarrhoea", "Not for bloody diarrhoea - see a doctor."),
    ("Taco 6 Tablet", "Loperamide + Ofloxacin", "Abbott", "TABLET", "-", "Strip of 6 tablets", 98.00, 108.00, 55, 1, "diarrhoea,antibiotic", ""),
    ("Emeset Tablet", "Ondansetron 4 mg", "Cipla", "TABLET", "4 mg", "Strip of 10 tablets", 62.00, 69.00, 95, 1, "diarrhoea", ""),
    ("Bendol 400 Tablet", "Albendazole 400 mg", "GSK", "TABLET", "400 mg", "Strip of 3 tablets", 42.00, 46.00, 130, 0, "worms", "One dose, repeat after 2 weeks."),
    ("Zentel Suspension 100ml", "Albendazole 200 mg/5 ml", "GSK", "SUSPENSION", "200 mg/5 ml", "100 ml bottle", 88.00, 96.00, 60, 0, "worms,child", ""),

    # ---- Constipation & piles ----
    ("Dulcolax Tablet", "Bisacodyl 5 mg", "Sanofi", "TABLET", "5 mg", "Strip of 10 tablets", 92.00, 99.00, 70, 0, "constipation", ""),
    ("Cremaffin Plus Liquid 200ml", "Liquid Paraffin + Milk of Magnesia", "Abbott", "SYRUP", "-", "200 ml bottle", 185.00, 199.00, 40, 0, "constipation", ""),
    ("Isabgol Husk Powder 100gm", "Psyllium Husk", "Sat-Isabgol", "POWDER", "-", "100 gm pack", 95.00, 105.00, 120, 0, "constipation", "With a full glass of water at night."),
    ("Smuth Gel", "Diltiazem 2% rectal", "Ajanta", "GEL", "2%", "15 gm tube", 168.00, 185.00, 35, 1, "piles", ""),
    ("Ardium 500 Tablet", "Hesperidin + Diosmin", "Intas", "TABLET", "500/450 mg", "Strip of 20 tablets", 245.00, 268.00, 30, 1, "piles", ""),

    # ---- Chronic: diabetes, BP, cholesterol, thyroid, heart ----
    ("Glycomet GP 0.5 Tablet", "Metformin + Glimepiride", "USV", "TABLET", "500/0.5 mg", "Strip of 15 tablets", 92.00, 101.00, 140, 1, "diabetes", "With or just after food."),
    ("Januvia 100 Tablet", "Sitagliptin 100 mg", "MSD", "TABLET", "100 mg", "Strip of 7 tablets", 265.00, 292.00, 45, 1, "diabetes", ""),
    ("Trulicity Pen", "Dulaglutide 0.75 mg", "Lilly", "DEVICE", "0.75 mg/0.5 ml", "1 pen", 3450.00, 3600.00, 8, 1, "diabetes", "Once weekly injection. Cold chain."),
    ("Human Mixtard Insulin 40IU", "Insulin (biphasic human)", "Novo Nordisk", "INJECTION", "40 IU/ml", "10 ml vial", 385.00, 419.00, 20, 1, "diabetes", "Keep refrigerated (2-8 C)."),
    ("Glucoburn Powder Sachet", "Berberine + Cinnamon + Bitter Melon", "Herbal", "POWDER", "-", "Pack of 30 sachets", 420.00, 465.00, 25, 0, "diabetes", ""),
    ("Ecosprin-75 Tablet", "Aspirin 75 mg", "USV", "TABLET", "75 mg", "Strip of 14 tablets", 12.00, 14.00, 220, 1, "heart", "After dinner."),
    ("Rosuvas 10 Tablet", "Rosuvastatin 10 mg", "Sun Pharma", "TABLET", "10 mg", "Strip of 10 tablets", 145.00, 159.00, 120, 1, "cholesterol,heart", "At night."),
    ("Atorva 10 Tablet", "Atorvastatin 10 mg", "Zydus", "TABLET", "10 mg", "Strip of 15 tablets", 98.00, 108.00, 130, 1, "cholesterol", ""),
    ("Telma 40 Tablet", "Telmisartan 40 mg", "Glenmark", "TABLET", "40 mg", "Strip of 15 tablets", 118.00, 130.00, 170, 1, "hypertension", "Same time every day."),
    ("Amlokind-AT Tablet", "Amlodipine + Atenolol", "Indus", "TABLET", "5/50 mg", "Strip of 15 tablets", 78.00, 86.00, 90, 1, "hypertension", ""),
    ("Neobloc 50 Tablet", "Nebivolol 50 mg", "Neomentums", "TABLET", "50 mg", "Strip of 15 tablets", 148.00, 162.00, 60, 1, "hypertension,heart", ""),
    ("Thyronorm 50mcg Tablet", "Thyroxine 50 mcg", "Abbott", "TABLET", "50 mcg", "Strip of 100 tablets", 175.00, 192.00, 80, 1, "thyroid", "Empty stomach, 30 min before tea."),
    ("Eltroxin 25mcg Tablet", "Thyroxine 25 mcg", "GSK", "TABLET", "25 mcg", "Strip of 100 tablets", 128.00, 141.00, 55, 1, "thyroid", ""),
    ("Zembris Tablet", "Fenofibrate 145 mg", "Zydus", "TABLET", "145 mg", "Strip of 10 tablets", 178.00, 195.00, 40, 1, "cholesterol", ""),

    # ---- Infections (antibiotics) ----
    ("Mox 500 Capsule", "Amoxicillin 500 mg", "Kalbaram", "CAPSULE", "500 mg", "Strip of 10 capsules", 98.00, 108.00, 110, 1, "antibiotic", "Complete the full course."),
    ("Augmentin 625 Tablet", "Amoxicillin + Clavulanic Acid", "GSK", "TABLET", "625 mg", "Strip of 10 tablets", 222.00, 244.00, 70, 1, "antibiotic", "With food to avoid nausea."),
    ("Azithral 500 Tablet", "Azithromycin 500 mg", "Alembic", "TABLET", "500 mg", "Strip of 5 tablets", 138.00, 152.00, 0, 1, "antibiotic", "Once daily - 3 or 5 day course."),
    ("Taxim-O Tablet", "Cefixime 200 mg", "Alkem", "TABLET", "200 mg", "Strip of 10 tablets", 198.00, 218.00, 85, 1, "antibiotic", ""),
    ("Cefspan 400 Capsule", "Cephalexin 500 mg", "Barley", "CAPSULE", "500 mg", "Strip of 10 capsules", 165.00, 180.00, 60, 1, "antibiotic", ""),
    ("Metrogyl Tablet", "Metronidazole 400 mg", "JBC", "TABLET", "400 mg", "Strip of 10 tablets", 32.00, 35.00, 120, 1, "antibiotic,diarrhoea", "No alcohol during the course."),
    ("Niftran 100 Tablet", "Nitrofurantoin 100 mg", "Aristo", "TABLET", "100 mg", "Strip of 10 tablets", 88.00, 96.00, 65, 1, "kidney,antibiotic", "For urine infection."),
    ("Citilox 500 Tablet", "Ciprofloxacin 500 mg", "Micro Labs", "TABLET", "500 mg", "Strip of 10 tablets", 88.00, 96.00, 95, 1, "antibiotic,kidney", ""),
    ("Rcin 300 Capsule", "Rifampicin 300 mg", "Macleods", "CAPSULE", "300 mg", "Bottle of 180 capsules", 620.00, 680.00, 12, 1, "tb,antibiotic", "TB regimen - DOTS centre."),

    # ---- Kidney, liver ----
    ("Uprise-D Tablet", "Drotaverine + Domperidone", "4D", "TABLET", "-", "Strip of 10 tablets", 88.00, 96.00, 50, 1, "kidney", ""),
    ("Citralite Powder 100gm", "Potassium Citrate + Magnesium", "Lupin", "POWDER", "-", "100 gm jar", 265.00, 292.00, 20, 1, "kidney", ""),
    ("Hepamerz Granules 5gm", "L-Ornithine L-Aspartate", "Sun Pharma", "POWDER", "5 gm", "Pack of 10 sachets", 385.00, 420.00, 18, 1, "liver", ""),
    ("Sylimarol Tablet", "Silymarin (Milk Thistle)", "Herbal", "TABLET", "140 mg", "Bottle of 60 tablets", 320.00, 350.00, 30, 0, "liver", ""),

    # ---- Nervous system, sleep, vitamins ----
    ("Alprax Tablet", "Alprazolam 0.25 mg", "Cipla", "TABLET", "0.25 mg", "Strip of 15 tablets", 68.00, 75.00, 40, 1, "anxiety", "Short term only. Habit forming."),
    ("Zolfresh Tablet", "Zolpidem 10 mg", "Sun Pharma", "TABLET", "10 mg", "Strip of 10 tablets", 98.00, 108.00, 30, 1, "anxiety", "Just before bed."),
    ("Serta 50 Tablet", "Sertraline 50 mg", "Sun Pharma", "TABLET", "50 mg", "Strip of 15 tablets", 165.00, 180.00, 35, 1, "anxiety", ""),
    ("Neurobion Forte Tablet", "Vitamin B-complex", "Merck", "TABLET", "-", "Strip of 20 tablets", 42.00, 46.00, 190, 0, "nerve,vitamins", ""),
    ("Methobalt Injection", "Methylcobalamin 500 mcg", "Aristo", "INJECTION", "500 mcg", "Ampoule", 32.00, 35.00, 80, 1, "nerve,anemia", ""),
    ("Succimax 50 Capsule", "Paracetamol + Caffeine + Domperidone", "Succi", "CAPSULE", "-", "Strip of 10 capsules", 58.00, 64.00, 0, 0, "headache", ""),
    ("Becosules Capsule", "Vitamin B-complex with C", "Pfizer", "CAPSULE", "-", "Strip of 20 capsules", 52.00, 57.00, 150, 0, "vitamins,immunity", ""),
    ("Limcee Tablet 500mg", "Vitamin C 500 mg (chewable)", "Abbott", "TABLET", "500 mg", "Strip of 15 tablets", 32.00, 35.00, 200, 0, "immunity,vitamins", ""),
    ("Shelcal 500 Tablet", "Calcium Carbonate + Vitamin D3", "Torrent", "TABLET", "500/250 IU", "Strip of 15 tablets", 98.00, 108.00, 140, 0, "vitamins,arthritis", ""),
    ("Uprise D3 60K Capsule", "Cholecalciferol 60000 IU", "4D", "CAPSULE", "60000 IU", "Strip of 4 capsules", 145.00, 160.00, 90, 0, "vitamins", "Once a week for 4 weeks."),
    ("Hemobit-D Syrup 200ml", "Iron + B12 + Folic Acid", "Mankind", "SYRUP", "-", "200 ml bottle", 178.00, 195.00, 55, 0, "anemia", "Stools may turn dark - normal."),
    ("Orofer XT Tablet", "Ferrous Ascorbate + Folic Acid", "Emcure", "TABLET", "100/1.5 mg", "Strip of 15 tablets", 168.00, 185.00, 85, 0, "anemia,womens", ""),
    ("Folvite 5mg Tablet", "Folic Acid 5 mg", "Pfizer", "TABLET", "5 mg", "Strip of 45 tablets", 42.00, 46.00, 160, 0, "anemia,womens", ""),
    ("Zincovit Tablet", "Multivitamin + Zinc", "Apex", "TABLET", "-", "Strip of 15 tablets", 98.00, 108.00, 175, 0, "immunity,vitamins", ""),

    # ---- Skin, eye, ear, dental ----
    ("Candid Dusting Powder", "Clotrimazole 1%", "Glenmark", "POWDER", "1%", "100 gm bottle", 128.00, 141.00, 70, 0, "allergy", "For fungal rash in folds."),
    ("Betadine Ointment 20gm", "Povidone Iodine 5%", "Win-Medicare", "OINTMENT", "5%", "20 gm tube", 95.00, 104.00, 100, 0, "first-aid", ""),
    ("Silverex Cream 20gm", "Silver Sulfadiazine 1%", "Centaur", "CREAM", "1%", "20 gm tube", 145.00, 159.00, 45, 1, "first-aid", "For burns."),
    ("Candid-B Cream", "Clotrimazole + Beclomethasone", "Glenmark", "CREAM", "-", "20 gm tube", 98.00, 108.00, 60, 1, "allergy", "Not on the face long term."),
    ("Lupicort Cream", "Hydrocortisone 1%", "Lupin", "CREAM", "1%", "20 gm tube", 78.00, 86.00, 50, 1, "allergy", ""),
    ("Refresh Tears Eye Drops", "Carboxymethylcellulose 0.5%", "Allergan", "DROPS", "0.5%", "10 ml drops", 145.00, 159.00, 65, 0, "eye", "Preservative free."),
    ("Moxin-LS Eye Drops", "Moxifloxacin 0.5%", "Alkem", "DROPS", "0.5%", "5 ml drops", 128.00, 140.00, 40, 1, "eye,antibiotic", ""),
    ("Ototop Suspension Drops", "Phenazone + Lidocaine", "Aristo", "DROPS", "-", "10 ml drops", 98.00, 108.00, 35, 1, "eye", "Ear pain - only if the eardrum is intact."),
    ("Bactident Gel", "Chlorhexidine 0.2%", "Ajanta", "GEL", "0.2%", "20 gm tube", 118.00, 129.00, 55, 0, "dental", ""),
    ("Dentogest Gum Paint", "Choline Salicylate + Benzalkonium", "GSK", "GEL", "-", "15 gm tube", 132.00, 145.00, 48, 0, "dental,child", ""),

    # ---- Women, child, men ----
    ("Meftal Spas Tablet", "Mefenamic Acid + Dicyclomine", "Blue Cross", "TABLET", "-", "Strip of 10 tablets", 78.00, 86.00, 90, 1, "womens,pain", "Period cramps."),
    ("Primolut N Tablet", "Norethisterone 5 mg", "Bayer", "TABLET", "5 mg", "Strip of 10 tablets", 128.00, 141.00, 40, 1, "womens", ""),
    ("Folvite Plus Tablet", "Folic Acid + B12 + Iron supplement", "Pfizer", "TABLET", "-", "Bottle of 30 tablets", 185.00, 205.00, 45, 0, "womens,anemia", ""),
    ("Cypon Syrup 150ml", "Cyproheptadine + Tricholine", "Woodlands", "SYRUP", "-", "150 ml bottle", 98.00, 108.00, 60, 0, "child", "Appetite stimulant."),
    ("Zincoderm Syrup 100ml", "Zinc + Amino acids", "Sun Pharma", "SYRUP", "-", "100 ml bottle", 155.00, 170.00, 38, 0, "child,immunity", ""),
    ("Ibifol Kids Gummies", "Multivitamin gummies", "Herbal", "GUMMY", "-", "Jar of 30", 285.00, 315.00, 22, 0, "child,vitamins", ""),

    # ---- First aid & hygiene ----
    ("Savlon Liquid 125ml", "Chlorhexidine + Cetrimide", "Johnson", "LIQUID", "-", "125 ml bottle", 118.00, 129.00, 120, 0, "first-aid,hygiene", "Dilute for wound cleaning."),
    ("Dettol Antiseptic Liquid 250ml", "Chloroxylenol 4.8%", "Reckitt", "LIQUID", "4.8%", "250 ml bottle", 155.00, 170.00, 130, 0, "first-aid,hygiene", ""),
    ("Betadine Solution 100ml", "Povidone Iodine 5%", "Win-Medicare", "LIQUID", "5%", "100 ml bottle", 185.00, 203.00, 75, 0, "first-aid", ""),
    ("Hand Sanitizer 500ml", "Isopropyl Alcohol 70%", "Lifebuoy", "LIQUID", "70%", "500 ml bottle", 165.00, 199.00, 90, 0, "hygiene", ""),
    ("Crepe Bandage 10cm", "Elastic compression bandage", "Bolin", "DEVICE", "10 cm x 4.5 m", "1 roll", 85.00, 99.00, 60, 0, "first-aid,pain", ""),
    ("Digital Thermometer", "Fever thermometer", "Dr Morepen", "DEVICE", "-", "1 unit", 199.00, 249.00, 40, 0, "first-aid,fever", ""),
    ("Pulse Oximeter", "SpO2 + pulse rate", "Dr Trust", "DEVICE", "-", "1 unit", 1450.00, 1699.00, 12, 0, "asthma,heart", ""),
    ("Dr Morepen BP Monitor", "Digital blood pressure monitor", "Dr Morepen", "DEVICE", "-", "1 unit", 1850.00, 2199.00, 10, 0, "hypertension", ""),
    ("Glucometer Strips (50)", "Test strips for blood sugar", "Dr Morepen", "DEVICE", "50 strips", "Box of 50", 620.00, 699.00, 25, 0, "diabetes", ""),
    ("Surgical Mask 3-Ply (50)", "Disposable face mask", "Medisafe", "DEVICE", "-", "Pack of 50", 145.00, 199.00, 80, 0, "hygiene", ""),
]


# ============================================================
# PARTNER CHEMISTS (the SQL side of the emergency search)
# ============================================================

NEARBY_SHOPS = [
    # name, address, area, phone, lat, lng, 24x7, hours, partner, rating,
    # {medicine name fragment: (stock, price)}
    (
        "Sanjeevani Partner Chemist - Malviya Nagar",
        "Shop 14, Malviya Nagar Road, Jaipur",
        "Malviya Nagar", "0141-2546110", 26.8715, 75.8015, True, "Open 24 hours",
        True, 4.4,
        {"Azithral": (14, 145.00), "Asthalin": (6, 132.00), "Human Mixtard": (4, 399.00),
         "Trulicity": (1, 3550.00), "Succimax": (22, 60.00), "Rcin": (3, 640.00)}
    ),
    (
        "Jyoti Medical Store",
        "C-Scheme, near Sindhi Camp, Jaipur",
        "Sindhi Camp", "0141-2371022", 26.9239, 75.8000, False, "09:00 - 22:30",
        True, 4.1,
        {"Azithral": (25, 141.00), "Dolo": (60, 33.00), "ORS": (120, 22.00),
         "Electral": (90, 21.00), "Pan 40": (40, 135.00)}
    ),
    (
        "Shree Ram Jan Aushadhi Kendra",
        "Sector 4, Mansarovar, Jaipur",
        "Mansarovar", "0141-2783344", 26.8440, 75.7700, False, "10:00 - 20:00",
        True, 4.6,
        {"Telma": (80, 105.00), "Glycomet": (70, 88.00), "Ecosprin": (200, 11.00),
         "Thyronorm": (40, 168.00), "Rosuvas": (35, 139.00)}
    ),
    (
        "Apollo Pharmacy - C-Scheme",
        "Ashok Marg, C-Scheme, Jaipur",
        "C-Scheme", "0141-5115115", 26.9101, 75.7901, True, "Open 24 hours",
        True, 4.5,
        {"Montek": (30, 182.00), "Asthalin": (12, 129.00), "Neurobion": (40, 44.00),
         "Refresh": (22, 152.00), "Augmentin": (18, 235.00)}
    ),
    (
        "MedPlus - Vaishali Nagar",
        "Goleda Road, Vaishali Nagar, Jaipur",
        "Vaishali Nagar", "0141-2756688", 26.9110, 75.7420, False, "09:30 - 22:00",
        True, 4.2,
        {"Azithral": (8, 143.50), "Savlon": (40, 121.00), "Isabgol": (25, 98.00),
         "Digital Thermometer": (10, 205.00)}
    ),
    (
        "New Jaipur Chemist (non-partner, listed)",
        "Sanganer Airport Road, Jaipur",
        "Sanganer", "0141-2791010", 26.8242, 75.8122, False, "08:00 - 23:00",
        False, 3.9, {}
    ),
]


# ============================================================
# SAMPLE PRESCRIPTION (so "Doctor prescribed" tab works right away)
# ============================================================

SAMPLE_PRESCRIPTION = {
    "diagnosis": "Acute bronchitis with low grade fever",
    "doctor_instructions": (
        "Plenty of warm fluids. Steam inhalation twice a day. Review after "
        "5 days if fever persists."
    ),
    "medicines": [
        # medicine name in the prescription, dosage, frequency, duration, note
        ("Dolo 650 Tablet", "650 mg", "Three times a day", "5 days", "After food"),
        ("Azithral 500 Tablet", "500 mg", "Once a day", "3 days", "After food"),
        ("Montek LC Tablet", "10/5 mg", "Once at night", "7 days", ""),
        ("Ascoril LS Syrup", "10 ml", "Three times a day", "5 days", "Shake before use"),
        ("Napa Extend 500 Tablet", "500 mg", "Twice a day", "3 days", "Not in our catalog yet"),
    ],
}


FORM_PHOTOS = {
    "TABLET": "tablet",
    "CAPSULE": "capsule",
    "SYRUP": "syrup",
    "SUSPENSION": "syrup",
    "POWDER": "powder",
    "GRANULES": "powder",
    "DROPS": "drops",
    "OINTMENT": "ointment",
    "CREAM": "ointment",
    "GEL": "ointment",
    "INJECTION": "injection",
    "SPRAY": "drops",
    "LOZENGE": "tablet",
    "LIQUID": "syrup",
    "DEVICE": "first-aid",
    "GUMMY": "tablet",
}


def image_path_for(form: str) -> str:
    """Prefer a real photo (jpg/png) and fall back to the drawn placeholder."""

    slug = FORM_PHOTOS.get((form or "TABLET").upper(), "tablet")
    folder = STATIC_DIR / "images" / "pharmacy"

    for extension in (".jpg", ".png"):
        if (folder / f"{slug}{extension}").exists():
            return f"images/pharmacy/{slug}{extension}"

    return f"images/pharmacy/{slug}.svg"


# ============================================================
# SEED
# ============================================================

def seed(reset: bool = False) -> int:

    from src.database.base import Base
    from src.database.connection import (
        DATABASE_BACKEND,
        DATABASE_LABEL,
        SessionLocal,
        engine
    )

    import src.models  # noqa: F401  (registers every table)

    from src.models.disease import Disease
    from src.models.doctor import Doctor
    from src.models.doctor_schedule import DoctorSchedule
    from src.models.medicine import Medicine
    from src.models.medicine_disease import MedicineDisease
    from src.models.nearby_pharmacy import (
        NearbyPharmacy,
        NearbyPharmacyStock
    )
    from src.models.pharmacy_cart import PharmacyCartItem
    from src.models.pharmacy_order import (
        PharmacyOrder,
        PharmacyOrderItem
    )
    from src.models.pharmacy_snapshot import PharmacySnapshot
    from src.models.prescription import Prescription
    from src.models.prescription_medicine import PrescriptionMedicine
    from src.models.user import User
    from src.security.password import hash_password
    from src.services import pharmacy_audit_service as audit
    from src.services import pharmacy_catalog_service as catalog
    from src.services import pharmacy_snapshot_service as snapshot_service

    print(f"Database: {DATABASE_LABEL}  ({DATABASE_BACKEND})")

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:

        if reset:
            print("--reset: clearing pharmacy rows (users and doctors kept)")
            for model in (
                PharmacyOrderItem,
                PharmacyOrder,
                PharmacyCartItem,
                MedicineDisease,
                NearbyPharmacyStock,
                NearbyPharmacy,
                Medicine,
                Disease,
                PrescriptionMedicine,
                Prescription,
            ):
                db.query(model).delete()
            db.commit()

        # ---------------- users ----------------
        created_users = []

        for name, email, phone, password, role in DEMO_USERS:
            user = db.query(User).filter(User.email == email).first()
            if user is None:
                user = User(
                    name=name,
                    email=email,
                    phone=phone,
                    password_hash=hash_password(password),
                    age=34,
                    gender="Male" if role != "PATIENT" else "Female",
                    role=role,
                    is_active=True,
                )
                db.add(user)
                db.flush()
                created_users.append(email)
            else:
                # Role is intentionally updated so an existing demo account
                # becomes a real SUPERUSER / PHARMACIST instead of PATIENT.
                if (user.role or "").upper() != role:
                    user.role = role
                user.is_active = True

        db.commit()

        if created_users:
            print(f"Logins created: {', '.join(created_users)}")
        else:
            print("Logins already existed (roles refreshed to match)")

        # ---------------- diseases ----------------
        disease_ids = {}

        for slug, label, group, icon in DISEASES:
            disease = db.query(Disease).filter(Disease.slug == slug).first()
            if disease is None:
                disease = Disease(
                    name=label, slug=slug, group_name=group, icon=icon,
                    description=f"Medicines commonly used for {label.lower()}.",
                    is_active=True
                )
                db.add(disease)
                db.flush()
            else:
                disease.name = label
                disease.group_name = group
                disease.icon = icon
            disease_ids[slug] = disease.id

        db.commit()
        print(f"Diseases / categories: {len(disease_ids)}")

        # ---------------- medicines ----------------
        added = 0
        updated = 0

        for row in MEDICINES:
            (name, generic, brand, form, strength, pack, price, mrp, stock,
             rx_only, tags, note) = row

            medicine = db.query(Medicine).filter(Medicine.name == name).first()

            if medicine is None:
                medicine = Medicine(sku=catalog.unique_sku(db, None), name=name)
                db.add(medicine)
                added += 1
            else:
                updated += 1

            medicine.generic_name = generic
            medicine.brand = brand
            medicine.form = form
            medicine.strength = strength
            medicine.pack_size = pack
            medicine.price = price
            medicine.mrp = mrp
            medicine.stock = stock
            medicine.low_stock_alert = 10
            medicine.requires_prescription = bool(rx_only)
            medicine.warning = (
                "Schedule H - doctor's prescription needed" if rx_only else None
            )
            medicine.description = (
                f"{generic}. {pack}. Used for {tags.replace(',', ', ')}."
            )
            medicine.dosage_info = note or None
            medicine.image_path = image_path_for(form)
            medicine.image_url = None
            medicine.is_active = True

            db.flush()

            for index, slug in enumerate(
                [part.strip() for part in tags.split(",") if part.strip()]
            ):
                disease_id = disease_ids.get(slug)
                if disease_id is None:
                    continue
                exists = (
                    db.query(MedicineDisease)
                    .filter(
                        MedicineDisease.medicine_id == medicine.id,
                        MedicineDisease.disease_id == disease_id
                    )
                    .first()
                )
                if exists is None:
                    db.add(MedicineDisease(
                        medicine_id=medicine.id,
                        disease_id=disease_id,
                        is_primary=(index == 0)
                    ))

        db.commit()
        print(f"Medicines: {added} added, {updated} refreshed")

        # ---------------- nearby partner shops ----------------
        shop_count = 0

        for (name, address, area, phone, lat, lng, open24, hours, partner,
             rating, stock_map) in NEARBY_SHOPS:

            shop = db.query(NearbyPharmacy).filter(NearbyPharmacy.name == name).first()

            if shop is None:
                shop = NearbyPharmacy(name=name)
                db.add(shop)
                shop_count += 1

            shop.address = address
            shop.area = area
            shop.city = "Jaipur"
            shop.pincode = "302001"
            shop.phone = phone
            shop.whatsapp = phone.replace("0", "91", 1) if phone else None
            shop.latitude = lat
            shop.longitude = lng
            shop.open_24x7 = bool(open24)
            shop.opening_hours = hours
            shop.is_partner = bool(partner)
            shop.rating = rating
            shop.is_active = True
            shop.sync_status = "MANUAL"
            shop.notes = (
                "Stock is updated by the pharmacy counter. Shown in the "
                "emergency 'find it nearby' list straight from SQL."
            )

            db.flush()

            for fragment, (qty, shop_price) in stock_map.items():

                medicine = (
                    db.query(Medicine)
                    .filter(Medicine.name.contains(fragment))
                    .first()
                )

                if medicine is None:
                    print(f"  ! no catalog match for '{fragment}' - skipped")
                    continue
                row = (
                    db.query(NearbyPharmacyStock)
                    .filter(
                        NearbyPharmacyStock.pharmacy_id == shop.id,
                        NearbyPharmacyStock.medicine_id == medicine.id
                    )
                    .first()
                )
                if row is None:
                    row = NearbyPharmacyStock(
                        pharmacy_id=shop.id, medicine_id=medicine.id
                    )
                    db.add(row)
                row.stock = qty
                row.price = shop_price
                row.trust = "VERIFIED"
                row.medicine_label = medicine.name
                row.updated_at = datetime.utcnow()

        db.commit()
        print(f"Partner chemists: {shop_count} added")

        # ---------------- doctors (only if this DB has none) ----------------
        doctors_added = 0

        if db.query(Doctor).count() == 0:
            for (d_name, d_email, d_phone, spec, qual, exp, fee) in DEMO_DOCTORS:
                db.add(Doctor(
                    name=d_name,
                    email=d_email,
                    phone=d_phone,
                    specialization=spec,
                    qualification=qual,
                    experience_years=exp,
                    languages="Hindi, English",
                    consultation_fee=fee,
                    bio=f"{spec} specialist at Sanjeevani Clinic.",
                    is_active=True,
                ))
                doctors_added += 1
            db.commit()
            print(f"Doctors: {doctors_added} added (this database had none)")

        # ---------------- doctor schedules (idempotent) ----------------
        # Every doctor is available Monday-Sunday, 10:00-14:00 in 5-minute
        # slots - the same grid the SQL setup file creates. Skipped for any
        # (doctor, day) that already has a row, so re-running never duplicates.
        from datetime import time as dtime

        schedules_added = 0
        for doctor in db.query(Doctor).filter(Doctor.is_active.is_(True)).all():
            for day_no in range(7):
                exists = (
                    db.query(DoctorSchedule)
                    .filter(
                        DoctorSchedule.doctor_id == doctor.id,
                        DoctorSchedule.day_of_week == day_no,
                    )
                    .first()
                )
                if exists:
                    continue
                db.add(DoctorSchedule(
                    doctor_id=doctor.id,
                    day_of_week=day_no,
                    start_time=dtime(10, 0),
                    end_time=dtime(14, 0),
                    slot_interval_minutes=5,
                    is_available=True,
                ))
                schedules_added += 1
        if schedules_added:
            db.commit()
            print(f"Doctor schedules: {schedules_added} added "
                  f"(10:00-14:00, Mon-Sun, 5-minute slots)")

        # ---------------- sample prescription ----------------
        patient = (
            db.query(User).filter(User.email == "patient@demo.com").first()
        )
        doctor = (
            db.query(Doctor)
            .filter(Doctor.specialization == "General Medicine")
            .first()
            or db.query(Doctor).first()
        )

        existing = (
            db.query(Prescription)
            .filter(Prescription.patient_id == patient.id)
            .filter(Prescription.diagnosis == SAMPLE_PRESCRIPTION["diagnosis"])
            .first()
        ) if patient else None

        if patient and doctor and existing is None:

            prescription = Prescription(
                patient_id=patient.id,
                doctor_id=doctor.id,
                diagnosis=SAMPLE_PRESCRIPTION["diagnosis"],
                doctor_instructions=SAMPLE_PRESCRIPTION["doctor_instructions"]
            )
            db.add(prescription)
            db.flush()

            for (med_name, dosage, frequency, duration, note) in SAMPLE_PRESCRIPTION["medicines"]:
                db.add(PrescriptionMedicine(
                    prescription_id=prescription.id,
                    medicine_name=med_name,
                    dosage=dosage,
                    frequency=frequency,
                    duration=duration,
                    instructions=note or None
                ))

            db.commit()
            print("Sample prescription added for patient@demo.com")

        elif existing is not None:
            print("Sample prescription already present")
        else:
            print(
                "Skipped the sample prescription "
                f"(patient present: {patient is not None}, doctor present: "
                f"{doctor is not None})"
            )

        # ---------------- demo clinic activity for the doctor desk ---------
        activity = seed_doctor_desk_demo(db)

        if any(activity.values()):
            print(
                "Doctor desk demo data: "
                + ", ".join(f"{count} {name}" for name, count in activity.items() if count)
            )
        else:
            print("Doctor desk demo data already present (nothing added)")

        # ---------------- first snapshot ----------------
        if db.query(PharmacySnapshot).count() == 0:
            super_user = (
                db.query(User).filter(User.role == "SUPERUSER").first()
            )
            snapshot_service.create_snapshot(
                db,
                label="Baseline after pharmacy seed",
                description=(
                    "Taken by seed_pharmacy.py so a bad edit can always be "
                    "rolled back to exactly this catalog."
                ),
                scope="PHARMACY",
                actor={
                    "user_id": super_user.id if super_user else None,
                    "name": "seed_pharmacy.py",
                    "role": "SYSTEM",
                },
                trigger="MANUAL",
                is_pinned=True
            )
            print("Baseline snapshot created (pinned)")

        audit.log_activity(
            db,
            action="pharmacy.system.seed",
            entity_type="system",
            entity_id=None,
            description=(
                f"Pharmacy seeded: {len(MEDICINES)} medicines, "
                f"{len(DISEASES)} diseases, {len(NEARBY_SHOPS)} nearby shops"
            ),
            severity="INFO",
            actor={"user_id": None, "name": "seed_pharmacy.py", "role": "SYSTEM"},
            commit=True
        )

        print("\nDone. Sign in at /login and open /pharmacy")
        return 0

    finally:
        db.close()



# ============================================================
# DEMO CLINIC ACTIVITY (so the doctor desk is not an empty shell)
# ============================================================

def seed_doctor_desk_demo(db) -> dict:
    """A small, realistic OPD history for the two demo patients.

    Everything here is guarded per table: if the patient already has
    appointments (i.e. this is a real clinic database), nothing is written.
    Dates are relative to today, so the numbers on the desk always look live
    instead of frozen at the day this file was written.
    """

    from datetime import date, time, timedelta

    from src.models.appointment import Appointment
    from src.models.doctor import Doctor
    from src.models.doctor_patient_note import DoctorPatientNote
    from src.models.follow_up import FollowUp
    from src.models.medical_record import MedicalRecord
    from src.models.treatment import Treatment
    from src.models.treatment_review import TreatmentReview
    from src.models.user import User

    from src.security.password import hash_password

    today = date.today()
    made = {"patients": 0, "appointments": 0, "records": 0,
            "treatments": 0, "follow_ups": 0, "reviews": 0, "notes": 0}

    patient = db.query(User).filter(User.email == "patient@demo.com").first()

    if patient is None:
        return made

    doctor_row = (
        db.query(Doctor).filter(Doctor.name == "Dr. Vikram Joshi").first()
        or db.query(Doctor).filter(Doctor.specialization == "General Medicine").first()
    )

    fee = float(doctor_row.consultation_fee or 500) if doctor_row else 500.0

    # a second, brand new patient so the "New" chip has something in it
    newcomer = db.query(User).filter(User.email == "sunita@demo.com").first()

    if newcomer is None:
        newcomer = User(
            name="Sunita Devi",
            email="sunita@demo.com",
            phone="9876543215",
            password_hash=hash_password("Demo@1234"),
            age=29,
            gender="Female",
            role="PATIENT",
            is_active=True,
        )
        db.add(newcomer)
        db.flush()
        made["patients"] += 1

    def add_appointment(person, offset_days, status, visit_type,
                        payment_status, amount, method, reason, start="11:30"):
        hour, minute = [int(part) for part in start.split(":")]
        end_minutes = minute + 15

        start_time = time(hour, minute)
        end_time = (time(hour, end_minutes) if end_minutes < 60
                    else time(hour + 1, end_minutes - 60))

        row = Appointment(
            patient_id=person.id,
            doctor_id=doctor_row.id if doctor_row else None,
            appointment_date=today + timedelta(days=offset_days),
            start_time=start_time,
            end_time=end_time,
            visit_type=visit_type,
            duration_minutes=15,
            status=status,
            reason=reason,
            payment_method=method,
            payment_status=payment_status,
            payment_amount=amount,
            refund_status="NOT_REQUIRED",
        )
        db.add(row)
        db.flush()
        made["appointments"] += 1
        return row

    # ---- the returning patient -------------------------------------------
    if db.query(Appointment).filter(Appointment.patient_id == patient.id).count() == 0:

        first = add_appointment(
            patient, -42, "COMPLETED", "General Consultation",
            "PAID", fee, "CASH",
            "Persistent headache and high BP reading at home"
        )
        add_appointment(
            patient, -14, "COMPLETED", "Follow-up",
            "PAID", fee, "UPI",
            "BP recheck after 4 weeks of tablets"
        )
        add_appointment(
            patient, -3, "COMPLETED", "Follow-up",
            "PENDING", fee, "CASH",
            "Felt dizzy once in the morning, wants report review"
        )
        add_appointment(
            patient, 6, "CONFIRMED", "Follow-up",
            "PENDING", fee, "CASH",
            "Routine 3-month BP check"
        )

        if db.query(MedicalRecord).filter(
            MedicalRecord.patient_id == patient.id
        ).count() == 0:
            record_one = MedicalRecord(
                patient_id=patient.id,
                doctor_id=doctor_row.id if doctor_row else None,
                appointment_id=first.id,
                visit_date=today - timedelta(days=42),
                chief_complaint="Headache for 10 days, BP 158/98 at home",
                symptoms=("Dull morning headache, occasional neck stiffness, "
                          "no vomiting, no visual loss"),
                clinical_notes=("Weight 74 kg, pulse 84/min regular, BP 160/96 "
                                "sitting, chest clear, no murmur"),
                diagnosis_notes="Essential hypertension, grade 1",
                treatment_summary=("Started telmisartan 40 mg once daily, low-salt "
                                   "diet, 30 min brisk walk, home BP log"),
                medicines="Tab Telmisartan 40 mg OD morning",
                doctor_instructions=("Come back in 4 weeks with the BP log. "
                                     "Report immediately if headache with vomiting."),
                status="COMPLETED",
            )
            db.add(record_one)
            db.add(MedicalRecord(
                patient_id=patient.id,
                doctor_id=doctor_row.id if doctor_row else None,
                visit_date=today - timedelta(days=14),
                chief_complaint="BP review",
                symptoms="No headache since starting the tablet",
                clinical_notes="BP 132/84, pulse 76. Adherence good.",
                diagnosis_notes="Hypertension - controlled on current dose",
                treatment_summary="Continue same dose, add yearly kidney panel",
                medicines="Tab Telmisartan 40 mg OD",
                doctor_instructions="Reduce salt at night, continue walking",
                status="FOLLOWUP_REQUIRED",
            ))
            db.flush()
            made["records"] += 2

            if doctor_row is not None and db.query(Treatment).filter(
                Treatment.patient_id == patient.id
            ).count() == 0:
                db.add(Treatment(
                    patient_id=patient.id,
                    medical_record_id=record_one.id,
                    doctor_id=doctor_row.id,
                    treatment_name="Blood pressure control programme",
                    description=("12-week plan: daily telmisartan, salt restriction, "
                                 "walking, home BP log, review every 4 weeks."),
                    start_date=today - timedelta(days=42),
                    end_date=today + timedelta(days=48),
                    status="ACTIVE",
                ))
                db.flush()
                made["treatments"] += 1

        if db.query(FollowUp).filter(
            FollowUp.patient_id == patient.id
        ).count() == 0:
            db.add(FollowUp(
                patient_id=patient.id,
                doctor_id=doctor_row.id if doctor_row else None,
                follow_up_date=today - timedelta(days=4),
                reason="Bring the home BP log for review",
                instructions="Call the clinic if you cannot come",
                status="PENDING",
            ))
            db.add(FollowUp(
                patient_id=patient.id,
                doctor_id=doctor_row.id if doctor_row else None,
                follow_up_date=today + timedelta(days=6),
                reason="3-month BP check with kidney panel report",
                instructions="Fast for 8 hours before the blood test",
                status="PENDING",
            ))
            db.flush()
            made["follow_ups"] += 2

        if doctor_row is not None and db.query(TreatmentReview).filter(
            TreatmentReview.patient_id == patient.id
        ).count() == 0:
            db.add(TreatmentReview(
                patient_id=patient.id,
                doctor_id=doctor_row.id,
                outcome="IMPROVED",
                current_condition="BETTER",
                experience="GOOD",
                follow_up_preference="IN_PERSON",
                change_reason="Head gone, BP steady at 130/85",
                rating=5,
                comment=("Tablet mil gaya pharmacy se, 5 minute me. Doctor ne "
                         "samajh ke samajhaya, ek hi visit me tension kam ho gayi."),
            ))
            db.flush()
            made["reviews"] += 1

    # ---- the brand new patient -------------------------------------------
    if newcomer is not None and db.query(Appointment).filter(
        Appointment.patient_id == newcomer.id
    ).count() == 0:
        add_appointment(
            newcomer, 2, "BOOKED", "General Consultation",
            "PENDING", fee, "CASH",
            "Two weeks of fever with body pain"
        )
        db.add(MedicalRecord(
            patient_id=newcomer.id,
            doctor_id=doctor_row.id if doctor_row else None,
            visit_date=today,
            chief_complaint="Fever 100.4F, body ache, mild cough",
            symptoms="Day 13 of fever, no breathlessness",
            clinical_notes="Chest clear, no rash, vitals stable",
            diagnosis_notes="Fever of unknown origin - investigations advised",
            treatment_summary="CBC, malaria antigen, dengue NS1; paracetamol PRN",
            medicines="Tab Dolo 650 SOS",
            doctor_instructions="Come back with reports in 2 days",
            status="FOLLOWUP_REQUIRED",
        ))
        db.flush()
        made["records"] += 1

    # ---- doctor notes on the file ---------------------------------------
    if db.query(DoctorPatientNote).filter(
        DoctorPatientNote.patient_id == patient.id
    ).count() == 0:
        author = db.query(User).filter(User.email == "doctor@demo.com").first()
        for (title, body, kind, pinned, urgent, visibility, offset) in (
            ("Allergic to penicillin",
             "Rash after amoxicillin in 2019. Avoid the whole penicillin family; "
             "azithromycin was tolerated last year.",
             "ALLERGY", True, True, "DOCTOR_ONLY", -42),
            ("Will not come unless reminded",
             "Works night shifts. Phone call works better than SMS - ask for a "
             "call on the day before.",
             "NOTE", True, False, "DOCTOR_ONLY", -14),
            ("Salt intake still high",
             "Keeps pickles and papad at night. Advised to shift dinner 2 hours "
             "earlier; recheck next visit.",
             "ADVISORY", False, False, "PATIENT_VISIBLE", -3),
        ):
            db.add(DoctorPatientNote(
                doctor_id=author.id if author else None,
                doctor_name=author.name if author else "Dr. Vikram Joshi",
                doctor_specialization=doctor_row.specialization if doctor_row else None,
                patient_id=patient.id,
                note_type=kind,
                title=title,
                body=body,
                visibility=visibility,
                is_pinned=pinned,
                is_urgent=urgent,
                status="ACTIVE",
                created_at=datetime.utcnow() - timedelta(days=abs(offset)),
                updated_at=datetime.utcnow() - timedelta(days=abs(offset)),
            ))
            made["notes"] += 1

    db.commit()
    return made

def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the pharmacy module")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete existing pharmacy rows first (users and doctors are kept)"
    )
    args = parser.parse_args()
    return seed(reset=args.reset)


if __name__ == "__main__":
    raise SystemExit(main())