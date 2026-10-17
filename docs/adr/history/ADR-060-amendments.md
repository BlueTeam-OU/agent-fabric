# ADR-060 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-17 — Accepted; the digest check is per file; sizes restated

The owner accepted the record in the coordinator's session ("adr 060 accepted", 2026-10-17). With it, round 2 of #289's blind review (review 5556925209) found four wordings that no longer matched: §5 rule 3 said each install records the digests of the files it installs, which leaves no digest for a file an earlier install wrote, so a later install that touches one file would refuse a launch for the other; it now says the record of an install is its signed commit's tree: the launcher renders the files of the last parent-signed commit on the directory, each blob checked against its object name, which is HEAD's tree on that path, so an edit committed after the install is the last commit and refuses (#290 round 1, F3, found the code keeps no per-file digests and needs none). §4 names that check. §1's legal-expert size was measured before #289's last brief change (24 714 at 98f0c746); it reads about 24 700. §8 now says the amendments to ADR-002, ADR-038 and ADR-042 land with the mechanism, and those to ADR-018, ADR-027 and ADR-057 with rule 8's stage, where that behaviour changes.
