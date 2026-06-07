# Health Literacy Wordlist
# Source: "Health Literacy Wordlist and Reading-Level Framework for Medication Queries"
# Covers Low (Grade 4–6), Moderate (Grade 7–9), and High (Grade 10+) literacy levels.
# Used by src/agents/orchestrator/literacy/scorer.py for deterministic vocabulary scoring.
#
# Organisation: each section maps to a subsection of the framework document so
# additions / audits can be done category-by-category.

# ---------------------------------------------------------------------------
# LOW HEALTH LITERACY  (Grade 4–6)
# Simple, everyday language. Emotional/safety focus. Non-medical vocabulary.
# ---------------------------------------------------------------------------

LOW_WORDS: list[str] = [
    # --- Basic medication terms (plain language) ---
    "pill", "pills", "my pills",
    "medicine", "my medicine",
    "shot",
    "my sugar pills", "sugar pills",
    "heart pill", "heart pills",
    "water pill", "water pills",
    "nerve pill", "nerve pills",
    "blood thinner",
    "the little blue pill", "big white one", "little white pill",
    "dr. smith's pill",

    # --- Example phrases (verbatim from framework) ---
    "what is this medicine for",
    "why do i take this pill",
    "is this pill for pain",
    "will this make me feel better",
    "can i stop taking it if i feel okay",
    "does it hurt my stomach",
    "will it make me sleepy",
    "why do i have to take it every day",
    "what does side effect mean",
    "is it okay to take this with food",
    "what happens if i miss a dose",
    "what happens if i miss a pill",
    "what happens if i miss one",
    "can i split my pill in half",
    "will it make me throw up",
    "is there a cheaper pill",
    "why do i need so many pills",
    "what's this pill for",
    "what does this medicine do",
    "why do i take it",
    "is this a must take",
    "doctor said it's for my heart",
    "doctor said it's for my sugar",
    "is it safe",
    "will this hurt me",
    "is this strong medicine",
    "what's a bad reaction",
    "how do i take my pills",
    "how many times a day",
    "does twice a day mean morning and night",
    "twice a day mean morning and night",
    "help me understand",
    "explain it easy",
    "just tell me the main thing",
    "i'm confused",
    "i am confused",
    "doctor said",

    # --- Symptom & side-effect language (plain) ---
    "i feel sick",
    "i feel bad",
    "i feel funny",
    "it makes me feel weird",
    "i just don't feel right",
    "i feel tired",
    "i feel sleepy",
    "i feel dizzy",
    "i feel woozy",
    "feel sick", "feel bad", "feel funny", "feel weird",
    "feel tired", "feel sleepy", "feel dizzy", "feel woozy",
    "feel better",
    "does it hurt my stomach",
    "hurt my stomach",
    "my head hurts",
    "my skin is itchy",
    "it makes my heart race",
    "i'm throwing up", "i am throwing up", "throwing up",
    "i can't sleep", "can't sleep",
    "i can't poop", "can't poop",
    "i have to pee all the time", "have to pee",

    # --- Core concerns ---
    "can i stop taking it", "can i stop",
    "can i drink juice", "can i drink beer",
    "beer with this", "juice with this",
    "my neighbor said this pill is bad",
    "neighbor said",
    "too expensive",
    "cheaper",
    "bad reaction",
    "is this a must",
    "just tell me",
    "miss a dose", "missed a dose",
    "split my pill",
    "morning and night",
    # Explicit low-level phrasing for food/timing questions (framework example)
    "is it okay to take this with food",
    "okay to take this with",
]

# Intent signals for LOW — question stems that indicate basic, direct queries
INTENT_LOW: list[str] = [
    "what is this",
    "what's this",
    "what does this",
    "why do i take",
    "why do i have to",
    "is it safe",
    "is this safe",
    "is it okay to",
    "will it",
    "will this",
    "can i stop",
    "help me understand",
    "explain it easy",
    "i'm confused",
    "what happens if i miss",
    "how do i take",
    "how many times",
    "is there a cheaper",
    "doctor said",
    "what's a bad",
]


# ---------------------------------------------------------------------------
# MODERATE HEALTH LITERACY  (Grade 7–9)
# Mix of everyday + basic medical vocabulary. Practical, structured questions.
# Aware of conditions and instructions. References pharmacist/pharmacy.
# ---------------------------------------------------------------------------

MODERATE_WORDS: list[str] = [
    # --- Basic medical terms ---
    "side effect", "side effects",
    "common side effects",
    "serious side effects",
    "antibiotic", "antibiotics",
    "painkiller", "pain killer",
    "antidepressant", "antidepressants",
    "sleeping pill", "sleeping pills",
    "inhaler",
    "injection",
    "insulin",
    "generic", "brand name",
    "pharmacist", "pharmacy",
    "statin",
    "diabetes medicine", "blood pressure medicine", "cholesterol medicine",

    # --- Health conditions (moderate-awareness) ---
    "diabetes", "infection", "high blood pressure",
    "allergy", "allergic",

    # --- Example phrases (verbatim from framework) ---
    "what are common side effects of this drug",
    "can i take it with breakfast",
    "can i take it with food",
    "is it safe with my allergy medicine",
    "how does it work",
    "how long before it starts working",
    "how long until it starts working",
    "what should i do if i get a rash",
    "can i take ibuprofen with my other pills",
    "can i exercise while taking this medication",
    "what happens if i feel tired after taking it",
    "how do i know if the medicine is working",
    "can antibiotics upset my stomach",
    "should i stop suddenly",
    "do i need extra blood tests for this medicine",
    "can i take it while pregnant",
    "can i take it while breastfeeding",
    "am i using my inhaler correctly",
    "pharmacist said it might interact",
    "safe to combine with alcohol",
    "can i take tylenol with this",
    "can i take advil with this",
    "does this interact with grapefruit",
    "what should i do if i miss a dose",
    "what if i'm breastfeeding",
    "when should i stop taking it",
    "do i need to taper off this medication",
    "is it safe with other medicines",
    "do i need to finish the whole bottle",
    "should i take it in the morning or night",

    # --- Symptom & side-effect language (moderate) ---
    "allergic reaction", "allergic reactions",
    "rash",
    "nausea",
    "constipation",
    "diarrhea",
    "drowsiness",
    "fatigue",
    "insomnia", "trouble sleeping",
    "weight gain", "weight loss",
    "upset stomach",
    "headache",
    "mood changes", "mood swings",

    # --- Practical-use terms ---
    # Note: standalone "interact/interaction/interactions" removed — too noisy as
    # substrings of high-literacy terms like "drug-drug interactions". Phrase-level
    # matches below are sufficient for moderate detection.
    "drug interaction", "drug interactions",
    "might interact", "could interact",
    "dose", "dosage",
    "directions", "instructions",
    "taper off", "tapering off", "taper",
    "stop suddenly",
    "blood test", "blood tests",
    "pregnant", "breastfeeding", "pregnancy",
    "exercise while taking",
    "can i drive",
    "driving while taking",
    "herbal supplement", "herbal supplements",
    "vitamins", "vitamin",
    "safe with", "safe during", "safe to combine",
    "with food", "with breakfast", "with water",
    "morning or night", "morning or evening",
    "finish the course", "finish the bottle",

    # --- Core concern indicators ---
    "risks",
    "how should i take this",
    "can i drink alcohol",
    "alcohol with this",
    "grapefruit",
    "ibuprofen", "tylenol", "advil",
    "supplements",
    "vitamins",
]

# Intent signals for MODERATE — structured practical questions
INTENT_MODERATE: list[str] = [
    "what are the side effects",
    "what are the common side effects",
    "what are the serious side effects",
    "what are the risks",
    "what happens if i feel",
    "how does it work",
    "how does this work",
    "how long before",
    "how long until",
    "can i take",
    "is it okay",
    "is it safe with",
    "what should i do if",
    "when should i",
    "do i need to",
    "should i take it",
    "can i exercise",
    "can i drink alcohol",
    "can i drive",
    "how do i know if",
    "do i need to taper",
    "pharmacist said",
]


# ---------------------------------------------------------------------------
# HIGH HEALTH LITERACY  (Grade 10+)
# Technical / pharmacological / clinical vocabulary. Analytical, multi-clause
# questions. References mechanisms, evidence, guidelines, clinical trials.
# ---------------------------------------------------------------------------

HIGH_WORDS: list[str] = [
    # --- Mechanism / pharmacology core terms ---
    "mechanism of action",
    "pharmacokinetics", "pharmacodynamic", "pharmacodynamics",
    "bioavailability",
    "half-life",
    "excretion", "excretion pathway",
    "metabolism",
    "hepatic metabolism", "hepatic gluconeogenesis",
    "renal function", "renal impairment",
    "hepatotoxicity",
    "nephrotoxicity",
    "CYP450", "CYP 450", "cyp450",
    "p-glycoprotein",
    "metabolites", "metabolite",
    "absorption", "distribution",

    # --- Clinical / adverse-effect terms ---
    "contraindications", "contraindication",
    "adverse effects", "adverse effect", "adverse events",
    "toxicity",
    "black box warning",
    "QT prolongation", "qt interval",
    "serotonin syndrome",
    "rhabdomyolysis",
    "teratogenic", "teratogenicity",
    "gastrointestinal motility",
    "hyponatremia",
    "hepatic impairment",
    "renal clearance",

    # --- Evidence / research / guidelines ---
    "evidence-based", "evidence based",
    "clinical trial", "clinical trials",
    "phase 3", "phase 2", "randomized controlled",
    "FDA approved", "FDA approval", "fda approved",
    "clinical guidelines", "treatment guidelines",
    "comparative efficacy",
    "off-label", "off label",
    "therapeutic indication", "therapeutic window",
    "pharmacovigilance",

    # --- Dosing / titration ---
    "titration", "dosage titration",
    "titrating the dosage",
    "dose escalation",

    # --- Genetics / precision medicine ---
    "pharmacogenomic", "pharmacogenomics",
    "drug-gene interaction", "drug gene interaction",
    "polymorphism", "polymorphisms",
    "genotype",

    # --- Drug classes (specific / technical names) ---
    "NSAID", "nsaid", "nsaids",
    "biguanide",
    "beta-lactam", "beta lactam",
    "SSRI", "ssri",
    "SNRI", "snri",
    "ACE inhibitor", "ace inhibitor",
    "ARB", "arb",
    "beta-blocker", "beta blocker",
    "monoclonal antibody", "monoclonal antibodies",
    "biologic", "biologics",
    "anticoagulant",
    "antihypertensive", "antihypertensives",

    # --- Specific generic drug names (high-signal when used correctly) ---
    "atorvastatin",
    "metformin",
    "sertraline",
    "lisinopril",
    "semaglutide",
    "warfarin",
    "clopidogrel",
    "omeprazole",
    "amlodipine",
    "losartan",

    # --- Example phrases (verbatim from framework) ---
    "what is the mechanism of action",
    "are there contraindications for renal impairment",
    "could this prolong my QT interval",
    "what are the potential drug-drug interactions",
    "is the dosage titration protocol fda-based",
    "how does hepatic metabolism affect efficacy",
    "what adverse effects were reported in clinical trials",
    "is there evidence for off-label use",
    "what are the pharmacokinetics in geriatric patients",
    "should i monitor for toxicity symptoms like hyponatremia",
    "is there a safer alternative in this drug class",
    "would titrating the dosage down reduce risk",
    "are there known interactions with antihypertensives",
    "is this medication recommended for refractory cases",
    "what should i do if i experience serotonin syndrome symptoms",
    "what is the bioavailability",
    "what is the half-life",
    "how does this drug interact with the cyp450 pathway",
    "how does it affect hepatic gluconeogenesis",
    "what is the dosage titration schedule",
    "what do the evidence-based guidelines say",
    "what is the comparative efficacy versus",
    "what did the phase 3 clinical trial data show",
    "is this fda approved for",
    "is this prescribed off-label",
    "antibiotic resistance",
    "refractory",
    "drug class",
    # Drug-drug interaction phrasing is high-literacy (vs "drug interaction" which is moderate)
    "drug-drug interaction", "drug-drug interactions",
    "potential drug-drug",
]

# Intent signals for HIGH — analytical/mechanistic question stems
INTENT_HIGH: list[str] = [
    "what is the mechanism",
    "mechanism of action",
    "what are the pharmacokinetics",
    "what is the bioavailability",
    "what is the half-life",
    "what are the contraindications",
    "how does this drug interact",
    "how does this interact with",
    "how does hepatic",
    "how does renal",
    "what does the evidence",
    "what did the",
    "what are the adverse",
    "is this fda approved",
    "is there evidence for",
    "off-label",
    "clinical trial",
    "dosage titration",
    "cyp450",
    "pharmacokinetics",
    "pharmacodynamics",
    "what is the comparative efficacy",
    "are there known interactions with",
    "recommended for refractory",
    "drug class",
    "phase 3",
    # Drug-drug phrasing is an unambiguous high-literacy signal
    "drug-drug",
    "what are the potential",
    "especially with ssri",
    "especially with snri",
]
