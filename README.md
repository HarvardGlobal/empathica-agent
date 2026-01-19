
## What this project does

Input
1. Public drug information pulled via API and normalized into structured entries
2. Example patients with medication lists, allergies, and key clinical context
3. Baseline test questions that act as a repeatable evaluation set

Core logic
1. Retrieval step fetches only the drug and patient facts needed for the question
2. Primary LLM drafts an answer at the right literacy level
3. Secondary LLM reviews the draft for guideline compliance, safety, and completeness, then returns the final answer or requests a revision

Output
1. Final user facing answer
2. Evidence payload listing which drug label fields and patient facts were used
3. Structured safety flags, for example interaction risk, contraindication risk, allergy risk, missing info

## Data entries

### 1. Drug knowledge base

Goal
Create a single normalized drug record format that can be populated from public sources and used for retrieval.

Suggested public sources
1. openFDA drug labeling for structured prescribing information sections
2. RxNorm for normalized drug names, identifiers, and mappings
3. DailyMed SPL access for label documents and structured product labeling
4. PubChem for chemical identifiers and selected properties when useful

Normalized drug record example
Each drug record should be stored as JSON with at least:

Core identifiers
• generic_name
• brand_names
• rxnorm_rxcui
• ndc_codes
• spl_id
• source_urls

Clinical sections
• indications_and_usage
• dosage_and_administration
• dosage_forms_and_strengths
• contraindications
• warnings_and_precautions
• adverse_reactions
• drug_interactions
• use_in_specific_populations
• boxed_warning

Metadata
• retrieved_at
• source_version
• parsing_notes

### 2. Example patients

Goal
Store synthetic or de identified example patients that support realistic medication reasoning tests.


Example patient record fields (FHIR aligned, minimal):
- `Patient.id`
- `Patient.birthDate` *(age can be derived from this)*
- `AllergyIntolerance[]` *(allergies)*
- `Condition[]` *(diagnoses, including pregnancy if applicable)*
- `MedicationRequest[]` *(prescribed medications, includes dose + frequency via `dosageInstruction`)*
- `MedicationStatement[]` *(what the patient is actually taking, optional but useful)*
- `Observation[]` *(key labs/vitals if relevant, e.g. eGFR, creatinine, ALT, AST)*
- `Patient.note` *(optional free text notes)*


### 3. Baseline test questions

Goal
Create a stable evaluation set that you can be run on every model update.

Example baseline questions
• Can I take Drug A with Drug B
• What are the major side effects of Drug A and when should I seek help
• I am allergic to penicillin, is Drug A safe
• I missed a dose of Drug A, what should I do
• Explain how to take Drug A in simple language
• Explain the same answer for a clinician audience

Each question should specify
• patient_id
• expected evidence fields to cite
• required safety checks
• target literacy level
• grading rubric

## System architecture

### Two stage generation and review

Stage 1
Primary LLM produces a draft answer grounded in retrieved drug facts and patient context.

Stage 2
Reviewer LLM checks that the answer
• follows safety and scope guidelines
• is consistent with retrieved evidence
• matches the user literacy level
• includes required disclaimers and escalation advice when appropriate
• avoids hallucinated dosing and avoids definitive medical directives

If it fails, the reviewer returns
• a corrected answer, or
• a structured revision request to rerun Stage 1 with constraints

### Literacy adaptation agent

Goal
Match answer complexity to the user.

Inputs
• user message features, reading complexity cues, prior interactions
• optional quick clarifying question if uncertainty is high

Outputs
• literacy_level label, for example patient basic, patient standard, clinician
• style constraints, for example define terms, avoid jargon, include analogies
• risk communication level, for example cautious, standard, high risk

Implementation options
• Rules first classifier as baseline
• Lightweight LLM classifier that outputs only a label and rationale tags
• Hybrid approach where rules handle obvious cases and LLM handles edge cases

### Retrieval

Goal
Keep the LLM grounded.

Implementation outline
• Drug ETL pulls and normalizes records into a local store
• Create embeddings for key sections and index them
• At query time retrieve top k relevant chunks
• Provide citations as source field names and ids, not free form web text

## Fine tuning plan

Recommended approach
1. Start with retrieval augmented prompting using a strong instruction tuned base model
2. Build a supervised fine tuning dataset from
   • baseline questions with ideal answers
   • multiple literacy variants per question
   • reviewer feedback and corrected outputs
3. Apply parameter efficient fine tuning, for example LoRA or QLoRA, to keep iteration fast
4. Add preference tuning later using pairwise comparisons, for example approved versus rejected drafts from the reviewer step

Training data format
• system prompt describing strict grounding and safety rules
• user message
• retrieved evidence payload
• assistant answer
• optional reviewer labels

Safety
• Exclude any samples that provide individualized medical instructions without appropriate caveats
• Emphasize escalation language and uncertainty handling
• Keep an explicit do not guess dosing rule unless present in retrieved label text

## Project structure

Suggested folders
• data
  • drugs_raw
  • drugs_normalized
  • patients
  • baseline_tests
• src
  • etl
  • retrieval
  • prompts
  • agents
  • llm
  • evaluation
  • api
• notebooks
• scripts
• docs

## Evaluation

Automated metrics
• groundedness score based on evidence overlap
• safety rule pass rate from reviewer outputs
• answer readability grade level, approximate
• baseline test accuracy and completeness

Human review
• clinician review on a small stratified sample
• focus on contraindications, interactions, dosing, escalation criteria

## Roadmap milestones and deliverables

### Milestone 1: Repository setup and project scaffolding
**Deliverables**
- Clean repo structure (`src/`, `data/`, `scripts/`, `docs/`)
- Environment setup (requirements, config templates, secrets handling)
- Basic logging + run scripts (CLI entrypoints)

---

### Milestone 2: Data schemas (drug + patient) and validation
**Deliverables**
- Normalized **Drug schema** (JSON) with required label sections
- Minimal **FHIR aligned Patient schema** for **2 example patients**
- JSON validation checks (schema validation + required fields)
- Documentation of field definitions and expected formats

---

### Milestone 3: Drug ETL pipeline (public data ingestion)
**Deliverables**
- ETL pipeline for at least one public drug data source
- Parsing and normalization into the Drug schema
- Versioned storage of raw vs normalized outputs
- Initial dataset of **50 to 200 normalized drug records**

---

### Milestone 4: Knowledge base build (indexing + retrieval ready)
**Deliverables**
- Chunking strategy for drug label sections (by category and headings)
- Embedding generation for chunks
- Retrieval index (FAISS or equivalent)
- Retrieval evaluation script (top-k sanity checks)

---

### Milestone 5: Example patients + grounding context builder
**Deliverables**
- **2 patient records** stored as FHIR style resources or a small Bundle-like format
- Patient context extraction function (med list, allergies, conditions, key observations)
- Evidence pack builder that merges:
  - retrieved drug chunks
  - patient context fields
  - query metadata

---

### Milestone 6: Baseline test suite (questions + expected checks)
**Deliverables**
- Baseline question set v1 (structured JSON)
- Each test includes:
  - patient reference
  - target literacy level
  - required safety checks (interactions, contraindications, allergies)
  - expected evidence fields to cite
- Evaluation runner that logs outputs + metadata
- Report template with pass/fail and error categories

---

### Milestone 7: Primary reasoning LLM (answer generation)
**Deliverables**
- System prompt and templates for grounded medication reasoning
- Primary LLM wrapper that only uses the evidence pack
- Output format definition:
  - final answer
  - cited evidence fields used
  - uncertainty and escalation statements when needed
- Baseline performance run and saved results

---

### Milestone 8: Literacy agent v1 (adaptive answer complexity)
**Deliverables**
- Literacy classifier (rule-based or lightweight LLM classifier)
- Literacy levels (example):
  - patient basic
  - patient standard
  - clinician
- Style guide mapping each level to constraints (tone, length, jargon control)
- A/B comparison on baseline tests (same question, different literacy outputs)

---

### Milestone 9: Reviewer LLM and safety gating (quality control)
**Deliverables**
- Reviewer rubric (structured checklist)
- Reviewer LLM that checks:
  - guideline compliance
  - grounding to evidence
  - safety completeness
  - literacy match
- Revision loop logic:
  - accept
  - reject with reasons
  - request rewrite with constraints
- Safety pass rate summary across baseline tests

---

### Milestone 10: Fine tuning v1 and final evaluation package
**Deliverables**
- Supervised dataset v1 generated from:
  - baseline questions
  - ideal answers
  - literacy variants
  - reviewer approved outputs
- LoRA or QLoRA fine tuning script
- Before/after comparison:
  - baseline test pass rate
  - reviewer rejection rate
  - readability targets per literacy level
- Final documentation package:
  - architecture overview
  - limitations and safety boundaries
  - reproducible run instructions
