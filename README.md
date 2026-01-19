
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

Milestone 1
Data foundation
Deliverables
• drug record schema
• ETL pipeline for at least one source
• 50 to 200 normalized drug records
• patient schema and 20 example patients

Milestone 2
Baseline evaluation harness
Deliverables
• baseline question set v1
• evaluation runner that logs results
• report template with pass fail and error categories

Milestone 3
RAG prototype
Deliverables
• retrieval index
• prompt templates
• working CLI or simple web API for Q and A

Milestone 4
Literacy agent v1
Deliverables
• literacy classifier baseline
• style guide mapping from level to constraints
• A B comparison on baseline tests

Milestone 5
Reviewer LLM and safety gating
Deliverables
• reviewer rubric and structured outputs
• automated rejection and revision loop
• safety pass rate dashboard

Milestone 6
Fine tuning v1
Deliverables
• supervised dataset v1
• LoRA or QLoRA training script
• before after comparison on baseline tests and readability targets

Milestone 7
End to end demo
Deliverables
• minimal UI
• trace view showing evidence and review outcome
• model card style documentation and limitations
