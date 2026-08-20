# Interview Questions — Honest Answers

---

**Q: Why did you actually build this?**
Management guidance only exists in earnings call transcripts as unstructured
text — there's no easy way to check later whether a management team delivered
on what they said. Investors end up relying on institutional memory rather
than data. I wanted to see if I could turn that into structured, queryable
data — extracting guidance with an LLM, then joining it against what actually
got reported.

**Q: Does it really solve a problem?**
At the scale I built it — one prototype, two real transcripts — no, it's not
something a fund would use today, and I won't pretend otherwise. What it
proves out is the workflow: can you reliably extract a structured claim from
unstructured text, and can you trust the extraction enough to act on it. The
validation step exists specifically to answer that second question, not just
the first.

**Q: Walk me through the pipeline.**
PDF transcript → pdfplumber text extraction → an LLM prompted to return
strict JSON guidance statements → every response validated against a schema
before being accepted → loaded into Postgres → joined against reported
financials to compare guidance against what actually happened.

**Q: What happens if the LLM returns malformed JSON?**
It's rejected, not silently coerced. `validate_item()` checks every required
field is present and every enum value (guidance_type, direction, confidence)
is one of the allowed values. I tested this directly — not just the happy
path, but fed it a deliberately broken item (missing fields, an invalid
guidance_type) and confirmed both get rejected with a specific reason logged.

**Q: You don't have an API key yet — so did any of this actually get tested?**
The extraction call itself, no — that's the one piece I can't test without a
key. Everything else has been run against real data: I downloaded and
extracted a real transcript before writing any code, built mock extraction
results modeled on what that real transcript actually said, and ran
validation, loading, and the guidance-vs-actuals join against that real
pipeline. The plumbing is proven; the model call is the one piece that isn't
yet.

**Q: What did you find, even with just two transcripts?**
Two things. First, a real result: Wipro guided "0% to 2.0% sequential revenue
growth" for Q4 FY26, and the actual reported figure was 2.89% — slightly
above the top of their own guided range. Second, adding the second transcript
immediately caught a real bug in my own mock extractor — it was hardcoded and
returned the same canned quote regardless of input, which would have silently
fabricated identical "guidance" for every company the moment I added more
data. Fixed it to genuine rule-based extraction, and that fix then honestly
revealed its own weakness: the keyword classifier mis-tagged Wipro's real
Q3FY24 revenue guidance as "qualitative" because that specific sentence
didn't contain the literal word "revenue." I didn't tune the regex to hide
that — it's exactly the kind of error the human-labelling step exists to
catch.

**Q: Why doesn't the join query automatically score guidance as right or
wrong?**
Because `stated_value` is free text — "0% to 2.0% sequential growth in
constant currency" — not a clean number. Parsing arbitrary guidance language
(ranges, qualifiers, YoY vs QoQ framing) into something auto-scorable is a
real NLP problem on its own. I chose to show guidance and actuals side by
side for a human to judge rather than fake a numeric pass/fail that the data
doesn't actually support.

**Q: What bug did you actually find and fix?**
The "next reported period after guidance" query was returning a period nine
months *before* the call date — because the transcripts table originally had
no date, only a label like "Q3FY26", so the query just picked each company's
earliest period on file. Fixed by extracting the actual call date from the
transcript's own header text via regex, and filtering the join on
`period_end > call_date`.

**Q: What would you do differently, or do next?**
Add more transcripts — I have two, enough to prove the pipeline genuinely
generalises across documents, not enough for a real accuracy claim. Improve
the mock classifier's `guidance_type` detection beyond simple keyword
matching (the Q3FY24 misclassification above is the concrete example of where
it breaks). And build the guidance-range parser — the biggest genuine
limitation of what's here today.

**Q: Your rule-based mock mode has real false positives — doesn't that
undermine the project?**
No, the opposite — a suspiciously perfect mock extractor would be the thing
to distrust. One of the 12 extracted items is literally an analyst's question
("I just wanted your thoughts on that vertical...") that got matched by the
regex and mis-tagged as guidance. I left it in rather than quietly filtering
it out, because that's precisely what the human-labelling step is for: a real
person reads `source_excerpt` against what got extracted and marks it wrong.
A validation process that never catches anything isn't validating anything.
