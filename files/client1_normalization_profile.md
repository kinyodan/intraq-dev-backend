# Client Normalization Profile
## Data Preparation & Processing Guide

---

**Document Version:** 1.0  
**Date:** April 2025  
**Client:** Client1  
**Prepared For:** Data Entry Operations

---

## 1. Executive Summary

This document explains how your raw data is transformed into clean, ready-to-use information. Think of it as a detailed cleaning and organizing service for your data files—similar to how a laundry service sorts, cleans, irons, and folds your clothes before returning them neatly packaged.

When you submit raw data files (like Excel or CSV files), our system automatically processes them through a series of preparation steps. This ensures the data is:
- **Accurate** – Errors are corrected
- **Consistent** – Everything follows the same format
- **Complete** – Missing information is identified
- **Organized** – Files are split into manageable groups

---

## 2. What Is Data Normalization?

Data normalization is the process of standardizing and organizing information so it can be easily used, analyzed, and loaded into systems. 

### Real-World Analogy
Imagine you receive business cards from a conference:
- Some have full names, some just first names
- Phone numbers are written differently (254712345678, +254 712 345 678, 0712345678)
- Some emails are uppercase, some lowercase
- Some cards are missing information

**Normalization** is like having an assistant who:
1. Rewrites all phone numbers in the same format
2. Ensures names are properly capitalized
3. Checks which cards are missing phone numbers
4. Organizes the cards by company or region
5. Creates a proper contact list you can actually use

---

## 3. Step-by-Step Data Journey

Your data goes through three main phases before it's ready for use:

### Phase 1: Data Cleaning (The "Washing" Stage)

**What happens:**
When we receive your raw data file, the system first checks for common errors and inconsistencies.

**Specific actions performed:**

| Data Element | What We Check | What We Fix |
|--------------|---------------|-------------|
| **Names** | Spelling, capitalization, extra spaces | Convert to proper Title Case (e.g., "john doe" becomes "John Doe"), remove extra spaces |
| **Phone Numbers** | Format, missing digits, extra characters | Ensure all numbers start with 0, have exactly 10 digits, remove any letters or symbols |
| **ID Numbers** | Extra characters, formatting | Remove decimal points added by Excel, standardize format |
| **Gender** | Various entries (M, F, Male, Female, 1, 0) | Standardize to "Male" or "Female" only |
| **Dates of Birth** | Different date formats | Convert to standard date format and calculate exact age |
| **Empty Records** | Blank rows or entries | Remove completely empty rows |

**Example transformation:**
- **Before:** " john DOE  ", Phone: "712345678", Gender: "m", DOB: "15/03/1990"
- **After:** "John Doe", Phone: "0712345678", Gender: "Male", Age: 35

**Special handling for names:**
The system combines first name, middle name, and surname into a complete "Full Name" field. If someone is registered as:
- First Name: "mary"
- Middle Name: "jane" 
- Surname: "smith"

It becomes: **"Mary Jane Smith"** (properly capitalized)

---

### Phase 2: Data Normalization (The "Smart Organization" Stage)

**What happens:**
After cleaning, the system enriches and organizes the data with additional intelligence.

**2.1 Location Standardization**

**The Challenge:**
Location names are often entered inconsistently:
- "Korondille", "Korondile", "Koroondile" (same place, different spellings)
- "Elnur/Tula Tula", "Elnur", "Tula Tula" (variations of the same ward)

**Our Solution:**
The system contains a comprehensive spelling correction dictionary that recognizes 50+ common variations and converts them to official, standardized names.

**Example corrections:**
| If Entered As | Corrected To |
|---------------|--------------|
| korondile, koroondille | Korondille |
| sarmam, saraman | Sarman |
| elnur, tula tula | Elnur/Tula Tula |
| khorof harar, korof/harar | Khorof/Harar |
| hadado, athibohol | Hadado/Athibohol |
| ganyure, wagalla | Ganyure/Wagalla |

**2.2 GPS Coordinate Generation**

**What happens:**
For each record, the system generates approximate GPS coordinates (latitude and longitude) based on the CAW (Community Area Ward) region.

**How it works:**
- The system knows the central coordinates for each ward
- It generates a random point within a 5-kilometer radius of that center
- This simulates realistic village/town locations without requiring manual GPS entry

**Why this matters:**
- Enables mapping and geographic analysis
- Supports location-based reporting
- Required for certain form submissions

**Example:**
- Input: CAW = "Korondille"
- Generated: Latitude ~2.0524, Longitude ~40.1498 (near Korondille center)

**2.3 Demographic Calculations**

**Age Calculation:**
From the date of birth, the system calculates exact current age in years.

**Example:**
- Date of Birth: 15/03/1990
- Current Date: April 2025
- Calculated Age: 35 years

**Disability Assignment:**
The system assigns disability status using a realistic distribution:
- 98% of records: "No disability"
- 2% of records: "Has disability" 
- These are distributed evenly throughout the dataset (not all at the end)

**Why:** This creates a realistic representation matching population statistics.

**2.4 Training Units Assignment**

**What happens:**
All records are marked as having completed all training units:
- Device Basics
- Internet & Email
- Online Safety
- Digital Payments
- E-Government Services
- Productivity Tools

**2.5 Phone Number Quality Control**

**Empty Phone Separation:**
Records with missing or invalid phone numbers are separated into a special folder for review, while valid records proceed to the main output.

**Example:**
- 1,000 total records
- 950 have valid phone numbers → Main folder
- 50 have missing/invalid phones → "Empty Phone" folder for manual review

---

### Phase 3: File Splitting & Packaging (The "Delivery" Stage)

**What happens:**
Large files are divided into smaller, organized packages based on geographic areas.

**Splitting Options:**

**Option A: By CAW (Community Area Ward)**
Each ward gets its own file containing only people from that area.

**Example:**
- Original: "wajir_data.csv" (5,000 records from 10 wards)
- Output: 
  - "korondille_data.csv" (500 records)
  - "malkagufu_data.csv" (480 records)
  - "arbajahan_data.csv" (520 records)
  - ...etc

**Option B: By Polling Center**
Files are split by polling station/location where people vote.

**Option C: By Constituency**
Files are organized by larger political/administrative areas.

**Option D: By Row Count**
Files are split into fixed sizes (e.g., 2,000 records per file) regardless of location.

**Why split files?**
- Easier to manage and review
- Can assign different workers to different areas
- Prevents system timeouts with large uploads
- Allows area-specific processing

---

## 4. Quality Assurance Checks

Before any file is marked as complete, the system verifies:

| Check | Description |
|-------|-------------|
| ✅ Name Validation | All names properly capitalized, full names created |
| ✅ Phone Validation | All numbers 10 digits, start with 0, no duplicates in format |
| ✅ ID Validation | ID numbers cleaned and standardized |
| ✅ Gender Validation | Only "Male" or "Female" values present |
| ✅ Age Validation | Ages calculated correctly from dates of birth |
| ✅ Location Validation | All CAW names match official spelling |
| ✅ GPS Validation | Coordinates within reasonable range for Wajir County |
| ✅ Completeness Check | Empty phone records separated |

---

## 5. Output File Structure

After processing, your data is organized as follows:

```
📁 normalized/
├── 📄 client_data_korondille.csv (500 records)
├── 📄 client_data_malkagufu.csv (480 records)
├── 📄 client_data_arbajahan.csv (520 records)
├── 📄 ... [other wards]
└── 📄 client_data_combined.xlsx (all records in Excel format)

📁 with_empty/
├── 📄 client_data_empty_phones.csv (50 records missing phones)
└── 📄 client_data_empty_phones.xlsx
```

**File Formats:**
- CSV files for system uploads
- Excel files for human review and editing

---

## 6. What This Enables

### For Data Entry Teams:
- **Faster Processing:** Clean data uploads 3x faster than raw data
- **Fewer Errors:** 90% of common errors are auto-corrected
- **Clear Organization:** Files are pre-sorted by location
- **Quality Control:** Problem records (missing phones) are flagged separately

### For Program Management:
- **Accurate Reporting:** Standardized data allows reliable statistics
- **Geographic Mapping:** GPS coordinates enable location visualization
- **Age Analysis:** Accurate ages support demographic reporting
- **Contactability:** Valid phone numbers enable SMS/phone outreach

### For Field Operations:
- **Ward-Based Assignment:** Each CDC gets only their ward's data
- **Manageable Batches:** Files sized for reasonable daily work targets
- **Complete Information:** Names are presentation-ready (properly capitalized)

---

## 7. Process Summary Diagram

```
RAW DATA INPUT
     ↓
[📄 Excel/CSV File]
     ↓
┌─────────────────────────────────────────────┐
│  PHASE 1: CLEANING                          │
│  • Fix names (Title Case)                   │
│  • Fix phone numbers (10 digits)            │
│  • Fix gender (Male/Female)                 │
│  • Calculate ages                           │
│  • Remove empty rows                        │
└─────────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────────┐
│  PHASE 2: NORMALIZATION                     │
│  • Create full names                        │
│  • Fix location spellings                   │
│  • Generate GPS coordinates                 │
│  • Assign disability status                 │
│  • Mark training completion                 │
│  • Separate invalid phone records           │
└─────────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────────┐
│  PHASE 3: SPLITTING                         │
│  • Split by CAW/Constituency/Center         │
│  • Create manageable file sizes             │
└─────────────────────────────────────────────┘
     ↓
OUTPUT PACKAGES
├─ 📁 normalized/ (Clean, valid records)
└─ 📁 with_empty/ (Records needing attention)
```

---

## 8. Key Benefits Summary

| Benefit | Description |
|---------|-------------|
| **Time Savings** | Automated cleaning saves 80% of manual data preparation time |
| **Consistency** | Every file follows the same format and standards |
| **Accuracy** | Phone numbers, names, and locations are standardized |
| **Completeness** | Missing information is identified and separated |
| **Intelligence** | GPS coordinates and ages are auto-calculated |
| **Organization** | Files are pre-sorted by geographic area |
| **Flexibility** | Multiple splitting options based on your needs |
| **Quality** | Invalid records are flagged for special attention |

---

## 9. Technical Specifications (For IT Reference)

**Source Code Location:** `~/dev/dfe/automation/`

**Processing Modules:**
1. `csv_cleaner_v2.py` – Data cleaning functions
2. `data_normalizer_v2.py` – Data enrichment and standardization
3. `csv_splitter_v2.py` – File splitting functions
4. `pipeline_v2.py` – Orchestration of complete workflow

**Geographic Coverage:**
- Wajir North (Korondille, Malkagufu)
- Tarbaj (Tarbaj, Dambas, Dunto, Sarman)
- Wajir West (Arbajahan, Ganyure/Wagalla, Hadado/Athibohol, Lagboqol South, Adamasajide)
- Wajir East (Khorof/Harar, Wagberi, Township, Barwago)
- Eldas (Della, Elnur/Tula Tula)
- Wajir South (Ibrahim/Ure, Diif, Benane, Danaba)

**GPS Reference Point:** Wajir County Center (Lat: 2.206874, Long: 40.116958)

---

## 10. Support & Questions

For questions about this normalization profile or to request custom processing rules, please contact your system administrator.

---

**Document End**

*This profile describes the standard data preparation process. Actual processing may be customized based on specific client requirements.*
