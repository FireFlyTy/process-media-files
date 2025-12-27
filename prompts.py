"""
Prompts for Document Classification and Extraction

Two-stage approach:
1. CLASSIFICATION - determine document type (separate prompts for PDF and Image)
2. EXTRACTION - type-specific detail extraction and validation

File types:
- PDF: documents, certificates, scanned papers
- Image: photos of damage, property, documents
"""

# =============================================================================
# STAGE 1: CLASSIFICATION - PDF
# =============================================================================

PDF_CLASSIFICATION_PROMPT = """You are a document classifier for a compensation claims system for displaced persons from Ukraine.

Your task: Determine the DOCUMENT TYPE and CREATION METHOD only.

## Document Categories:

### 1. official_certificate
Official documents from GOVERNMENT bodies (ДСНС, ОВА, City Council, Ministry).
IDENTIFYING FEATURES:
- Official LETTERHEAD at top with government body name, emblem, address
- Organization names include: "ДСНС", "DSNS", "Державна служба", "ОВА", "Військова адміністрація", "Military Administration", "Міська рада", "City Council", "Міністерство"
- Document REGISTRATION NUMBER (e.g., "№ 1247/03-12", "вих. № 234")
- Signatures with OFFICIAL TITLES/RANKS (підполковник, начальник, captain, head of department)
- Round STATE stamp with emblem or authority name

### 2. damage_act  
Damage acts created by RESIDENTS or OSBB (not government).
IDENTIFYING FEATURES:
- NO official government letterhead
- Text starts with "Ми, що нижче підписалися..." or "We, the undersigned..."
- Signatures are REGULAR CITIZENS (names only, no official titles)
- May have OSBB stamp (круглa печатка ОСББ) - NOT government stamp
- No official registration number

### 3. photo_collection
PDF containing ONLY PHOTOS with no or minimal document text.
IDENTIFYING FEATURES:
- Pages contain photographs, not document scans
- No letterhead, no stamps, no signatures
- May have simple captions under photos
- Used to submit multiple damage photos as single PDF

### 4. identity_document
Passport, ID card, driver's license scans.
IDENTIFYING FEATURES:
- Contains person's PHOTO
- Has document series and number
- Contains personal data (name, birth date, etc.)

### 5. property_document
Property ownership documents, registry extracts.
IDENTIFYING FEATURES:
- Contains property ADDRESS
- Has owner information
- Registry extract number or certificate number
- May have QR code for verification

### 6. financial_statement
Bank statements, account documents.
IDENTIFYING FEATURES:
- Bank/financial institution name
- Account numbers
- Transaction history or balance
- Date range

### 7. utility_bill
Utility bills, proof of residence.
IDENTIFYING FEATURES:
- Service provider name (gas, electric, water)
- Service address
- Account number
- Payment amount/period

### 8. court_decision
Court decisions, legal rulings.
IDENTIFYING FEATURES:
- Court name in header
- Case number
- "РІШЕННЯ", "ПОСТАНОВА", "УХВАЛА"
- Judge name(s)

### 9. registration_extract
Extracts from state registries.
IDENTIFYING FEATURES:
- Registry name (державний реєстр)
- Extract number
- QR code or verification code
- Official stamp

### 10. medical_record
Medical documents, certificates.
IDENTIFYING FEATURES:
- Medical institution name
- Doctor's signature
- Diagnosis or medical information
- Patient name

### 11. application_form
Filled application forms.
IDENTIFYING FEATURES:
- Form structure with fields
- Filled-in personal data
- May be partially handwritten

### 12. other
Does not fit any category above.

## Creation Method:
1. **scanned** - Scanned paper document
   Signs: paper texture, slight rotation, scan artifacts, uneven lighting, visible paper edges
2. **digital_native** - Created digitally  
   Signs: perfect alignment, clean background, crisp text, no paper texture
3. **photo_converted** - Photographed document saved as PDF
   Signs: perspective distortion, shadows, uneven lighting, background visible
4. **screenshot** - Screenshot saved as PDF (RED FLAG!)
   Signs: UI elements, status bar, browser chrome, screen artifacts
5. **unknown** - Cannot determine

## CRITICAL DECISION RULES:
Rule 1: If you see GOVERNMENT LETTERHEAD (ДСНС, ОВА, etc.) → official_certificate (NOT damage_act)
Rule 2: If document has ONLY photos with no official text → photo_collection
Rule 3: If signatures have TITLES/RANKS → likely official_certificate
Rule 4: If signatures are just citizen names → likely damage_act
Rule 5: Screenshot = always add to red_flags

## IMAGE DETECTION:

Count any photographs, pictures, or photo-like images in the document.
DO NOT count: logos, emblems, stamps, signatures, QR codes, form graphics.
COUNT: photos of damage, rooms, buildings, people, attached photo evidence.

Respond ONLY with JSON:
{
    "document_type": "<category>",
    "document_type_ua": "<тип українською>",
    "creation_method": "<method>",
    "brief_description": "<one sentence describing what you see>",
    "has_images": <true/false - are there PHOTOS in the document?>,
    "images_count": <number of photos found, 0 if none>,
    "images_pages": [<list of page numbers with photos>],
    "classification_confidence": <0.0-1.0>,
    "classification_reasoning": "<why you chose this type>",
    "red_flags": ["<only if screenshot or obvious problems>"]
}"""


# =============================================================================
# STAGE 1: CLASSIFICATION - IMAGE
# =============================================================================

IMAGE_CLASSIFICATION_PROMPT = """You are an image classifier for a compensation claims system for displaced persons from Ukraine.

Your task: Determine the IMAGE CATEGORY and what it shows.

## Image Categories:

### 1. damage_photo
Photo showing DAMAGE to property (building, apartment, house, vehicle).
IDENTIFYING FEATURES:
- Visible destruction: holes, cracks, collapsed structures
- Debris, broken glass, burn marks
- Damaged furniture or appliances
- War-related damage (shelling, explosions)

### 2. property_exterior
Photo of building/property EXTERIOR (may or may not show damage).
IDENTIFYING FEATURES:
- Building facade, entrance, yard
- Street view of property
- May show address or building number

### 3. property_interior
Photo of building/property INTERIOR (may or may not show damage).
IDENTIFYING FEATURES:
- Rooms, corridors, stairs
- Furniture, appliances
- Interior condition documentation

### 4. document_photo
Photo of a PAPER DOCUMENT (not scan, actual photo).
IDENTIFYING FEATURES:
- Paper document visible in frame
- May have perspective distortion
- Background visible around document
- Shadows, uneven lighting

### 5. identity_photo
Photo for identification purposes or photo of ID document.
IDENTIFYING FEATURES:
- Person's face visible
- Or: ID card/passport photographed

### 6. before_after
Photo showing property BEFORE damage (for comparison).
IDENTIFYING FEATURES:
- Clean, intact property
- No visible damage
- Often older photo quality
- Context suggests "before" state

### 7. screenshot
Screenshot from phone/computer - RED FLAG!
IDENTIFYING FEATURES:
- Status bar visible (time, battery, signal)
- Browser chrome or app UI
- Screen interface elements
- Perfect rectangular edges

### 8. other
Does not fit categories above.

## CRITICAL RULES:
Rule 1: If you see STATUS BAR, BROWSER UI, or APP INTERFACE → screenshot (RED FLAG)
Rule 2: Analyze ACTUAL content - what does the photo SHOW?
Rule 3: For damage: describe SPECIFIC damage visible (holes, cracks, debris)
Rule 4: If photo shows clean/intact property → NOT damage_photo (unless context is "before")

## DAMAGE VERIFICATION:

REAL DAMAGE looks like:
- Holes in walls/ceiling/roof
- Collapsed structures
- Debris and rubble
- Burn marks, fire damage
- Shattered windows
- Destroyed furniture/appliances

NOT DAMAGE (don't classify as damage_photo):
- Clean, normal rooms
- Intact furniture
- Working appliances
- Minor wear and tear
- Mess/clutter (not destruction)

Respond ONLY with JSON:
{
    "category": "<category from list>",
    "category_ua": "<категорія українською>",
    "brief_description": "<what the image shows>",
    "shows_damage": <true/false>,
    "damage_description": "<specific damage visible, or null>",
    "damage_severity": "<none/minor/moderate/severe/catastrophic or null>",
    "classification_confidence": <0.0-1.0>,
    "classification_reasoning": "<why you chose this category>",
    "red_flags": ["<only if screenshot or fake/stock photo detected>"]
}"""


# =============================================================================
# STAGE 2: IMAGE ANALYSIS (independent from text)
# =============================================================================

IMAGE_ANALYSIS_PROMPT = """You are analyzing IMAGES/PHOTOS extracted from a document.

IMPORTANT: You are seeing ONLY the images, not the document text.
Your task: Describe what each image shows OBJECTIVELY, without any context from document text.

## For EACH image, determine:

### 1. Content Type:
- damage_photo: Shows property damage (holes, cracks, debris, destruction)
- room_interior: Shows room/interior (may or may not have damage)
- building_exterior: Shows building from outside
- document_scan: Shows a scanned document or certificate
- person_photo: Shows a person (ID photo, portrait)
- other: Anything else

### 2. If shows property/room - Damage Assessment:

REAL DAMAGE indicators:
- Structural holes (through walls, ceiling, floor)
- Collapsed structures (fallen ceiling, walls)
- Debris, rubble, broken materials on floor
- Burn marks, charring, fire damage
- Shattered windows, broken glass
- Exposed wiring, pipes, insulation
- Water damage stains, flooding evidence
- Cracks in walls/ceiling (structural, not cosmetic)

NOT DAMAGE (normal condition):
- Clean, intact surfaces
- Working furniture and appliances
- Normal wear and tear
- Clutter or mess (not destruction)
- Minor scratches or scuffs
- Peeling paint (age, not damage)

### 3. Authenticity Check:
- Is this a real photo or screenshot?
- Signs of editing or manipulation?
- Stock photo watermarks?
- Inconsistent lighting or shadows?

## Response format:

Respond ONLY with JSON:
{
    "images_analyzed": <number>,
    "images": [
        {
            "image_index": 1,
            "content_type": "<damage_photo/room_interior/building_exterior/document_scan/person_photo/other>",
            "description": "<detailed description of what you see>",
            "shows_damage": <true/false>,
            "damage_details": {
                "present": <true/false>,
                "types": ["<hole/crack/collapse/burn/debris/water/shattered_glass/none>"],
                "severity": "<none/minor/moderate/severe/catastrophic>",
                "specific_description": "<what exactly is damaged and how>"
            },
            "condition": "<destroyed/severely_damaged/damaged/minor_damage/intact/clean>",
            "authenticity": {
                "appears_genuine": <true/false>,
                "concerns": ["<screenshot/edited/stock_photo/inconsistent - if any>"]
            }
        }
    ],
    "overall_summary": {
        "total_images": <number>,
        "images_showing_damage": <number>,
        "images_showing_intact": <number>,
        "damage_types_found": ["<list of damage types across all images>"],
        "overall_damage_severity": "<none/minor/moderate/severe/catastrophic>",
        "images_appear_consistent": <true/false - same location/property?>,
        "authenticity_score": <0.0-1.0>
    }
}"""


# =============================================================================
# STAGE 3: EXTRACTION PROMPTS (per document type)
# =============================================================================

OFFICIAL_CERTIFICATE_PROMPT = """You are extracting details from an OFFICIAL GOVERNMENT CERTIFICATE (dovідka, act, certificate from ДСНС, ОВА, or other government body).

{image_analysis_section}

## REQUIRED ELEMENTS (must be present):
1. ✓ Official letterhead with government body name
2. ✓ Document registration number and date
3. ✓ Official round stamp (державна печатка)
4. ✓ Signature(s) with titles/positions
5. ✓ Issuing authority name

## EXTRACTION CHECKLIST:

### Letterhead:
- Is there an official header? (government body name, address, contacts)
- What organization is shown?

### Document Details:
- Document number (номер документа)
- Document date (дата)
- What is the document about? What damage/situation is described in TEXT?

### Stamps:
- Is there a round official stamp visible?
- Can you read the stamp text? What authority?
- Location on page (usually bottom, near signatures)

### Signatures:
- How many signatures?
- Are there titles/ranks next to signatures? (підполковник, начальник, etc.)
- Are signatures handwritten marks or just printed lines?

### CROSS-VALIDATION (if image analysis provided):
Compare TEXT CLAIMS with IMAGE ANALYSIS RESULTS.
- What does the TEXT claim about damage?
- What do IMAGES actually show (from image_analysis)?
- Do they MATCH or MISMATCH?

MISMATCH EXAMPLES (red_flag):
- Text claims "roof destroyed" but images show intact ceiling
- Text claims "severe fire damage" but images show no burn marks
- Text describes damage but images show clean, intact rooms
- Text claims specific damage type but images show different damage

## VALIDATION RULES:
- Missing letterhead → red_flag
- Missing stamp → red_flag  
- Missing signature → red_flag
- No document number → warning
- Images don't match text claims → red_flag (CRITICAL!)
- Digital document (not scanned) → warning only

Respond ONLY with JSON:
{
    "issuing_authority": "<government body name>",
    "document_number": "<number or null>",
    "document_date": "<YYYY-MM-DD or null>",
    "document_subject": "<what document is about>",
    "text_damage_claims": "<what the TEXT says about damage>",
    "has_letterhead": <true/false>,
    "letterhead_authority": "<organization from letterhead>",
    "has_stamp": <true/false>,
    "stamp_authority": "<text from stamp if readable>",
    "stamp_location": "<where on page>",
    "has_signatures": <true/false>,
    "signatures_count": <number>,
    "signatures_have_titles": <true/false>,
    "signatures_details": ["<title/name for each>"],
    "content_summary": "<key information from document TEXT>",
    "cross_validation": {
        "text_claims": "<what text claims about damage>",
        "image_shows": "<what images actually show - from image_analysis>",
        "match_status": "<full_match/partial_match/mismatch/no_images>",
        "mismatch_details": "<specific discrepancies if any, or null>"
    },
    "red_flags": ["<missing elements, mismatches, problems>"],
    "warnings": ["<minor issues>"],
    "extraction_confidence": <0.0-1.0>
}"""


OFFICIAL_CERTIFICATE_PROMPT_NO_IMAGES = """You are extracting details from an OFFICIAL GOVERNMENT CERTIFICATE (dovідka, act, certificate from ДСНС, ОВА, or other government body).

This document has NO PHOTOS - analyze text and official elements only.

## REQUIRED ELEMENTS (must be present):
1. ✓ Official letterhead with government body name
2. ✓ Document registration number and date
3. ✓ Official round stamp (державна печатка)
4. ✓ Signature(s) with titles/positions
5. ✓ Issuing authority name

## EXTRACTION CHECKLIST:

### Letterhead:
- Is there an official header? (government body name, address, contacts)
- What organization is shown?

### Document Details:
- Document number (номер документа)
- Document date (дата)
- What is the document about?

### Stamps:
- Is there a round official stamp visible?
- Can you read the stamp text? What authority?
- Location on page (usually bottom, near signatures)

### Signatures:
- How many signatures?
- Are there titles/ranks next to signatures? (підполковник, начальник, etc.)
- Are signatures handwritten marks or just printed lines?

## VALIDATION RULES:
- Missing letterhead → red_flag
- Missing stamp → red_flag  
- Missing signature → red_flag
- No document number → warning
- Digital document (not scanned) → warning only

Respond ONLY with JSON:
{
    "issuing_authority": "<government body name>",
    "document_number": "<number or null>",
    "document_date": "<YYYY-MM-DD or null>",
    "document_subject": "<what document is about>",
    "has_letterhead": <true/false>,
    "letterhead_authority": "<organization from letterhead>",
    "has_stamp": <true/false>,
    "stamp_authority": "<text from stamp if readable>",
    "stamp_location": "<where on page>",
    "has_signatures": <true/false>,
    "signatures_count": <number>,
    "signatures_have_titles": <true/false>,
    "signatures_details": ["<title/name for each>"],
    "content_summary": "<key information from document>",
    "red_flags": ["<missing required elements or problems>"],
    "warnings": ["<minor issues>"],
    "extraction_confidence": <0.0-1.0>
}"""


DAMAGE_ACT_PROMPT = """You are extracting details from a DAMAGE ACT created by RESIDENTS or OSBB (not a government document).

{image_analysis_section}

## EXPECTED ELEMENTS:
1. ✓ List of witnesses/signatories (usually 2-3 people)
2. ✓ Signatures of witnesses
3. ✓ Date of act creation
4. ✓ Property address
5. ✓ Description of damage
6. Optional: OSBB stamp (not required)

## EXTRACTION CHECKLIST:

### Signatories:
- How many people signed?
- Are they listed by name?
- Are signatures visible (handwritten marks)?

### Property Info:
- What is the property address?
- Owner name?
- Property type (apartment, house)?

### Damage Description (from TEXT):
- What damage is described in text?
- Date when damage occurred?
- Cause of damage?

### Stamp:
- Is there an OSBB stamp? (acceptable but not required)
- Is there a government stamp? (unusual for resident act)

### CROSS-VALIDATION (if image analysis provided):
Compare TEXT CLAIMS with IMAGE ANALYSIS RESULTS.
- What does the TEXT claim about damage?
- What do IMAGES actually show (from image_analysis)?
- Do they MATCH or MISMATCH?

## VALIDATION RULES:
- Fewer than 2 signatures → warning
- No signatures at all → red_flag
- No property address → red_flag
- Government stamp present → warning (unusual, verify if really resident act)
- Images don't match text claims → red_flag (CRITICAL!)

Respond ONLY with JSON:
{
    "property_address": "<address or null>",
    "owner_name": "<name or null>",
    "damage_date": "<YYYY-MM-DD when damage occurred, or null>",
    "act_date": "<YYYY-MM-DD when act was created, or null>",
    "text_damage_claims": "<what the TEXT says about damage>",
    "damage_cause": "<cause: shelling, rocket, etc.>",
    "witnesses_count": <number>,
    "witnesses_names": ["<list of names>"],
    "has_signatures": <true/false>,
    "signatures_count": <number>,
    "has_osbb_stamp": <true/false>,
    "osbb_name": "<OSBB name if visible>",
    "has_government_stamp": <true/false>,
    "content_summary": "<key information from TEXT>",
    "cross_validation": {
        "text_claims": "<what text claims about damage>",
        "image_shows": "<what images actually show - from image_analysis>",
        "match_status": "<full_match/partial_match/mismatch/no_images>",
        "mismatch_details": "<specific discrepancies if any, or null>"
    },
    "red_flags": ["<problems found, including mismatches>"],
    "warnings": ["<minor issues>"],
    "extraction_confidence": <0.0-1.0>
}"""


PHOTO_COLLECTION_PROMPT = """You are analyzing a PDF that contains a COLLECTION OF PHOTOS (not a document scan).

## YOUR TASK:
1. Count the photos
2. Describe what EACH photo shows
3. For damage claims: verify photos show ACTUAL damage

## PHOTO ANALYSIS:

For EACH photo, describe:
- What is shown (room, building exterior, object)?
- What is the condition?
- Is there visible damage?

## DAMAGE VERIFICATION:

REAL DAMAGE looks like:
- Broken/collapsed walls or ceiling
- Holes, cracks in structures
- Debris on floor
- Burn marks, fire damage
- Shattered windows
- Destroyed furniture

NOT DAMAGE:
- Clean, intact rooms
- Normal furniture
- Working appliances
- Minor wear and tear

## CHECK FOR:
- Are these original photos or screenshots? (screenshots = red_flag)
- Do photos appear edited or manipulated?
- Are photos consistent (same location)?

Respond ONLY with JSON:
{
    "photo_count": <number>,
    "photos_analysis": [
        {
            "photo_number": 1,
            "description": "<what is shown>",
            "shows_damage": <true/false>,
            "damage_type": "<type if damage visible, else null>"
        }
    ],
    "overall_damage_visible": <true/false>,
    "damage_types_found": ["<list of damage types>"],
    "appears_to_be_same_location": <true/false>,
    "screenshots_detected": <true/false>,
    "editing_signs_detected": <true/false>,
    "content_summary": "<overall description>",
    "red_flags": ["<problems: screenshots, no damage, editing>"],
    "warnings": ["<minor issues>"],
    "extraction_confidence": <0.0-1.0>
}"""


IDENTITY_DOCUMENT_PROMPT = """You are extracting details from an IDENTITY DOCUMENT (passport, ID card, driver's license).

## EXTRACTION CHECKLIST:

### Document Type:
- What type of ID? (passport, ID card, driver's license)
- Country of issue?

### Personal Data (extract if visible):
- Full name
- Date of birth
- Document number
- Issue date / Expiry date

### Security Features:
- Is holder's photo visible?
- Does photo appear genuine (not glued/edited)?
- Any signs of tampering?

## VALIDATION:
- No photo visible → warning
- Signs of editing/tampering → red_flag
- Document appears expired → warning
- Poor quality making data unreadable → warning

Respond ONLY with JSON:
{
    "document_subtype": "<passport/id_card/driver_license/other>",
    "country": "<issuing country>",
    "holder_name": "<full name or null>",
    "date_of_birth": "<YYYY-MM-DD or null>",
    "document_number": "<number or null>",
    "issue_date": "<YYYY-MM-DD or null>",
    "expiry_date": "<YYYY-MM-DD or null>",
    "has_photo": <true/false>,
    "photo_appears_genuine": <true/false/null>,
    "data_readable": <true/false>,
    "red_flags": ["<tampering signs, etc.>"],
    "warnings": ["<minor issues>"],
    "extraction_confidence": <0.0-1.0>
}"""


PROPERTY_DOCUMENT_PROMPT = """You are extracting details from a PROPERTY DOCUMENT (ownership certificate, registry extract).

## EXTRACTION CHECKLIST:

### Property Info:
- Property address
- Property type (apartment, house, land)
- Area/size

### Owner Info:
- Owner name(s)
- Ownership share (if multiple owners)

### Document Details:
- Document/extract number
- Issue date
- Registry name
- QR code or verification code present?

### Official Elements:
- Stamp present?
- Signature present?

## VALIDATION:
- No property address → red_flag
- No owner name → red_flag
- No document number → warning
- No stamp on registry extract → warning

Respond ONLY with JSON:
{
    "property_address": "<address>",
    "property_type": "<apartment/house/land/commercial/other>",
    "property_area": "<size with units or null>",
    "owner_names": ["<list of owners>"],
    "ownership_shares": ["<shares if specified>"],
    "document_number": "<number or null>",
    "document_date": "<YYYY-MM-DD or null>",
    "registry_name": "<registry name or null>",
    "has_qr_code": <true/false>,
    "has_stamp": <true/false>,
    "has_signature": <true/false>,
    "red_flags": ["<problems>"],
    "warnings": ["<minor issues>"],
    "extraction_confidence": <0.0-1.0>
}"""


UTILITY_BILL_PROMPT = """You are extracting details from a UTILITY BILL.

## EXTRACTION CHECKLIST:

### Provider Info:
- Service provider name
- Service type (gas, electricity, water, heating)

### Account Info:
- Service address
- Account number
- Account holder name

### Billing Info:
- Billing period
- Amount due
- Payment status (if visible)

## VALIDATION:
- No address → red_flag
- No provider name → warning
- No account number → warning

Note: Utility bills often don't have stamps/signatures - this is normal.

Respond ONLY with JSON:
{
    "provider_name": "<company name>",
    "service_type": "<gas/electricity/water/heating/other>",
    "service_address": "<address>",
    "account_number": "<number or null>",
    "account_holder": "<name or null>",
    "billing_period": "<period or null>",
    "amount": "<amount or null>",
    "currency": "<UAH/USD/EUR/null>",
    "red_flags": ["<problems>"],
    "warnings": ["<minor issues>"],
    "extraction_confidence": <0.0-1.0>
}"""


# =============================================================================
# STAGE 2: EXTRACTION PROMPTS - IMAGE
# =============================================================================

DAMAGE_PHOTO_EXTRACTION_PROMPT = """You are analyzing a DAMAGE PHOTO for a compensation claim.

## YOUR TASK:
1. Describe the damage in detail
2. Identify what is damaged (building part, room, object)
3. Assess damage severity
4. Check for signs of fake/stock photos

## EXTRACTION CHECKLIST:

### Damage Details:
- What specific damage is visible?
- What part of building/property? (ceiling, wall, floor, roof, window)
- What room/area? (kitchen, bedroom, living room, exterior)
- What caused the damage? (if determinable: shelling, fire, explosion)

### Severity Assessment:
- **minor**: Small cracks, broken window, surface damage
- **moderate**: Holes in walls, partial collapse, significant destruction
- **severe**: Large structural damage, multiple rooms affected
- **catastrophic**: Building uninhabitable, total destruction

### Authenticity Check:
- Does this look like a real photo (not stock photo)?
- Consistent lighting and perspective?
- Any watermarks or stock photo indicators?
- Does it match typical war damage patterns?

## RED FLAGS:
- Stock photo watermarks
- Unrealistic lighting/composition
- Image appears professionally staged
- Metadata suggests download from internet

Respond ONLY with JSON:
{
    "damage_type": ["<list of damage types: hole, crack, collapse, fire, debris, broken_window, etc>"],
    "damaged_objects": ["<what is damaged: ceiling, wall, floor, furniture, appliance, etc>"],
    "location_in_building": "<room or area>",
    "damage_cause": "<shelling/fire/explosion/unknown>",
    "damage_severity": "<minor/moderate/severe/catastrophic>",
    "damage_description": "<detailed description>",
    "appears_authentic": <true/false>,
    "authenticity_concerns": ["<any concerns or empty list>"],
    "content_summary": "<brief summary>",
    "red_flags": ["<problems found>"],
    "warnings": ["<minor issues>"],
    "extraction_confidence": <0.0-1.0>
}"""


PROPERTY_PHOTO_EXTRACTION_PROMPT = """You are analyzing a PROPERTY PHOTO (exterior or interior).

## YOUR TASK:
1. Describe what is shown
2. Note property condition
3. Identify any visible damage
4. Extract any visible addresses or identifiers

## EXTRACTION CHECKLIST:

### Property Details:
- Type of view (exterior/interior)
- Building type (apartment building, house, commercial)
- Specific area shown (facade, entrance, room type)

### Condition:
- Overall condition (good, fair, poor, damaged)
- Any visible damage?
- Signs of recent renovation or neglect?

### Identifiable Information:
- Visible address or building number?
- Any signs or labels?
- Identifiable landmarks?

Respond ONLY with JSON:
{
    "view_type": "<exterior/interior>",
    "building_type": "<apartment/house/commercial/other>",
    "area_shown": "<specific area or room>",
    "condition": "<good/fair/poor/damaged>",
    "has_damage": <true/false>,
    "damage_description": "<if damage visible, describe it>",
    "visible_address": "<address if visible, else null>",
    "identifiable_features": ["<list of identifiable elements>"],
    "content_summary": "<brief summary>",
    "red_flags": [],
    "warnings": [],
    "extraction_confidence": <0.0-1.0>
}"""


DOCUMENT_PHOTO_EXTRACTION_PROMPT = """You are analyzing a PHOTO OF A DOCUMENT (not a scan, an actual photograph).

## YOUR TASK:
1. Identify what document is photographed
2. Check if text is readable
3. Note any visible official elements

## EXTRACTION CHECKLIST:

### Document Identification:
- What type of document is this?
- What language?
- Is it official or personal?

### Readability:
- Is text legible?
- Any parts obscured or cut off?
- Photo quality sufficient?

### Official Elements (if visible):
- Stamps visible?
- Signatures visible?
- Letterhead visible?

### Photo Quality Issues:
- Blur or focus problems?
- Glare or shadows?
- Document fully in frame?

Respond ONLY with JSON:
{
    "document_type_visible": "<what document appears to be>",
    "language": "<document language>",
    "text_readable": <true/false/partial>,
    "has_visible_stamp": <true/false>,
    "has_visible_signature": <true/false>,
    "has_visible_letterhead": <true/false>,
    "document_date_visible": "<date if readable, else null>",
    "key_information": "<any readable key info>",
    "photo_quality": "<good/acceptable/poor>",
    "quality_issues": ["<list of issues: blur, glare, cropped, etc>"],
    "content_summary": "<brief summary>",
    "red_flags": [],
    "warnings": [],
    "extraction_confidence": <0.0-1.0>
}"""


IDENTITY_PHOTO_EXTRACTION_PROMPT = """You are analyzing an IDENTITY PHOTO or photo of an ID document.

## YOUR TASK:
1. Determine if this is a portrait photo or photo of ID document
2. Extract visible information
3. Check for authenticity

## PHOTO TYPES:

### Portrait Photo (for identification):
- Face clearly visible?
- Photo quality suitable for identification?
- Neutral background?
- Any signs of manipulation?

### ID Document Photo (passport, ID card photographed):
- What type of document?
- Is holder's photo visible?
- What data is readable?
- Signs of tampering?

## AUTHENTICITY CHECK:
- Does photo appear genuine (not photoshopped)?
- Consistent lighting?
- Any cut/paste artifacts?
- Any signs of document tampering?

## RED FLAGS:
- Face obscured or unclear
- Signs of photo manipulation
- Document appears altered
- Multiple faces or inconsistencies

Respond ONLY with JSON:
{
    "photo_type": "<portrait/id_document_photo>",
    "face_visible": <true/false>,
    "face_quality": "<good/acceptable/poor/not_applicable>",
    "document_type_if_id": "<passport/id_card/driver_license/other/null>",
    "country_if_id": "<country of document if identifiable, else null>",
    "readable_data": {
        "name": "<if visible, else null>",
        "document_number": "<if visible, else null>",
        "date_of_birth": "<if visible, else null>",
        "expiry_date": "<if visible, else null>",
        "other_info": "<any other visible data>"
    },
    "appears_authentic": <true/false>,
    "authenticity_concerns": ["<list any concerns>"],
    "photo_quality": "<good/acceptable/poor>",
    "content_summary": "<brief description>",
    "red_flags": ["<only if manipulation detected or serious issues>"],
    "warnings": ["<minor issues>"],
    "extraction_confidence": <0.0-1.0>
}"""


SCREENSHOT_EXTRACTION_PROMPT = """You are analyzing what appears to be a SCREENSHOT.

Screenshots are generally NOT ACCEPTED as valid evidence. Document what you see.

## EXTRACTION:
- What app/website is shown?
- What content is displayed?
- Why might someone submit this?

Respond ONLY with JSON:
{
    "screenshot_source": "<app/website/system>",
    "content_shown": "<what is displayed>",
    "contains_relevant_info": <true/false>,
    "info_description": "<what relevant info if any>",
    "content_summary": "<brief summary>",
    "red_flags": ["Screenshot submitted instead of original document/photo"],
    "warnings": [],
    "extraction_confidence": <0.0-1.0>
}"""

# =============================================================================
# PROMPT MAPPINGS
# =============================================================================

# PDF document type → extraction prompt
PDF_EXTRACTION_PROMPTS = {
    "official_certificate": OFFICIAL_CERTIFICATE_PROMPT,
    "damage_act": DAMAGE_ACT_PROMPT,
    "photo_collection": PHOTO_COLLECTION_PROMPT,
    "identity_document": IDENTITY_DOCUMENT_PROMPT,
    "property_document": PROPERTY_DOCUMENT_PROMPT,
    "utility_bill": UTILITY_BILL_PROMPT,
    "court_decision": OFFICIAL_CERTIFICATE_PROMPT,
    "registration_extract": OFFICIAL_CERTIFICATE_PROMPT,
    "medical_record": OFFICIAL_CERTIFICATE_PROMPT,
    "financial_statement": UTILITY_BILL_PROMPT,
    "application_form": DAMAGE_ACT_PROMPT,
    "other": None,
}

# Image category → extraction prompt
IMAGE_EXTRACTION_PROMPTS = {
    "damage_photo": DAMAGE_PHOTO_EXTRACTION_PROMPT,
    "property_exterior": PROPERTY_PHOTO_EXTRACTION_PROMPT,
    "property_interior": PROPERTY_PHOTO_EXTRACTION_PROMPT,
    "document_photo": DOCUMENT_PHOTO_EXTRACTION_PROMPT,
    "identity_photo": IDENTITY_PHOTO_EXTRACTION_PROMPT,
    "before_after": PROPERTY_PHOTO_EXTRACTION_PROMPT,
    "screenshot": SCREENSHOT_EXTRACTION_PROMPT,
    "other": None,
}

# Backward compatibility alias
EXTRACTION_PROMPTS = PDF_EXTRACTION_PROMPTS


# =============================================================================
# GETTER FUNCTIONS
# =============================================================================

def get_pdf_classification_prompt() -> str:
    """Get the PDF classification prompt."""
    return PDF_CLASSIFICATION_PROMPT


def get_image_classification_prompt() -> str:
    """Get the image classification prompt."""
    return IMAGE_CLASSIFICATION_PROMPT


def get_classification_prompt(file_type: str) -> str:
    """Get classification prompt based on file type."""
    if file_type == "pdf":
        return PDF_CLASSIFICATION_PROMPT
    elif file_type == "image":
        return IMAGE_CLASSIFICATION_PROMPT
    else:
        return IMAGE_CLASSIFICATION_PROMPT  # Default to image


def get_pdf_extraction_prompt(document_type: str) -> str | None:
    """Get extraction prompt for PDF document type."""
    return PDF_EXTRACTION_PROMPTS.get(document_type)


def get_image_extraction_prompt(category: str) -> str | None:
    """Get extraction prompt for image category."""
    return IMAGE_EXTRACTION_PROMPTS.get(category)


def get_extraction_prompt(type_or_category: str, file_type: str = "pdf") -> str | None:
    """
    Get the appropriate extraction prompt.

    Args:
        type_or_category: document_type (for PDF) or category (for image)
        file_type: "pdf" or "image"

    Returns:
        Extraction prompt string or None
    """
    if file_type == "pdf":
        return PDF_EXTRACTION_PROMPTS.get(type_or_category)
    elif file_type == "image":
        return IMAGE_EXTRACTION_PROMPTS.get(type_or_category)
    else:
        # Try both mappings
        return PDF_EXTRACTION_PROMPTS.get(type_or_category) or IMAGE_EXTRACTION_PROMPTS.get(type_or_category)


def get_image_analysis_prompt() -> str:
    """Get the image analysis prompt for Stage 2."""
    return IMAGE_ANALYSIS_PROMPT


def format_image_analysis_section(image_analysis: dict | None) -> str:
    """
    Format image analysis results for injection into extraction prompt.

    Args:
        image_analysis: Results from Stage 2 image analysis, or None

    Returns:
        Formatted string to inject into prompt
    """
    if not image_analysis:
        return ""

    lines = [
        "## ⚠️ IMAGE ANALYSIS RESULTS (FACTS - DO NOT DISPUTE!):",
        "",
        "The following image descriptions were obtained by INDEPENDENT analysis.",
        "These descriptions are AUTHORITATIVE - do not contradict them.",
        "Your task is to COMPARE these with document TEXT claims.",
        "",
    ]

    images = image_analysis.get("images", [])
    if not images:
        lines.append("No images were found in this document.")
        return "\n".join(lines)

    for img in images:
        idx = img.get("image_index", "?")
        content_type = img.get("content_type", "unknown")
        description = img.get("description", "No description")
        shows_damage = img.get("shows_damage", False)

        damage_info = ""
        if shows_damage:
            details = img.get("damage_details", {})
            severity = details.get("severity", "unknown")
            types = details.get("types", [])
            damage_info = f" | DAMAGE: {severity}, types: {', '.join(types)}"
        else:
            condition = img.get("condition", "unknown")
            damage_info = f" | NO DAMAGE - condition: {condition}"

        lines.append(f"**Image {idx}** [{content_type}]: {description}{damage_info}")

    # Add summary
    summary = image_analysis.get("overall_summary", {})
    if summary:
        lines.append("")
        lines.append("**SUMMARY:**")
        lines.append(f"- Total images: {summary.get('total_images', 0)}")
        lines.append(f"- Images showing damage: {summary.get('images_showing_damage', 0)}")
        lines.append(f"- Images showing intact: {summary.get('images_showing_intact', 0)}")
        lines.append(f"- Overall damage severity: {summary.get('overall_damage_severity', 'none')}")
        if summary.get('damage_types_found'):
            lines.append(f"- Damage types found: {', '.join(summary['damage_types_found'])}")

    lines.append("")

    return "\n".join(lines)


def get_extraction_prompt_with_images(
    document_type: str,
    file_type: str = "pdf",
    image_analysis: dict | None = None
) -> str | None:
    """
    Get extraction prompt with image analysis injected.

    Args:
        document_type: document_type (for PDF) or category (for image)
        file_type: "pdf" or "image"
        image_analysis: Results from Stage 2 image analysis, or None

    Returns:
        Formatted extraction prompt with image analysis section
    """
    # Get base prompt
    prompt = get_extraction_prompt(document_type, file_type)
    if not prompt:
        return None

    # If no images, use prompt without image section
    if not image_analysis or not image_analysis.get("images"):
        # Remove the placeholder if present
        prompt = prompt.replace("{image_analysis_section}", "")
        return prompt

    # Format image analysis section
    image_section = format_image_analysis_section(image_analysis)

    # Inject into prompt
    if "{image_analysis_section}" in prompt:
        return prompt.replace("{image_analysis_section}", image_section)
    else:
        # Prepend if no placeholder
        return image_section + "\n\n" + prompt