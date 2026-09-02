q41
AD full verbatim: 

Despite the schema linker returning low entropy scores, the phrase 'connected to' is inherently ambiguous across the four Person->Incident relationship types (SUSPECTED_OF, WITNESSED, VICTIM_OF, INVESTIGATES). The linker has collapsed onto one interpretation (SUSPECTED_OF via ASSOCIATED_WITH chain), but 'connected to' reasonably maps to any of the four role edges, each returning a structurally different query and a different set of people. The schema linker's confident score here reflects a single candidate selection, not the true semantic breadth of 'connected to'.





q105
The OWNS relationship carries active/from_date/to_date properties, meaning there could be both current and historical owners. 'Who owns' could reasonably mean the current owner (active:true) or all past and present owners. Despite the schema linker returning a single candidate with score 1.00 (not distinguishing between filtered and unfiltered), this temporal ambiguity is inherent in the schema and the question does not specify whether current or historical ownership is intended."

- note: score here refers to the Schema Linker's own per-candidate confidence (softmax). score of 1 means SL only has 1 candidate for that relationship slot (nothing to spread probability across)
- since score is 1 here, entropy is 0