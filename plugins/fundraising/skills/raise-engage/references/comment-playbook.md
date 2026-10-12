# Comment playbook — joining a public thread without pitching it

The point of a comment is not reach. It is that **one specific person** in that thread — the
partner who wrote it, the operator who asked the question, the founder whose investor is reading —
learns that you know something real about the problem. Everything below follows from that.

## What gets a reply
1. **Answer the open question, not the post.** Read the comments first. The thread's open
   questions are usually in the replies ("how do you handle schema changes?", "who owns
   permissions?", "does this work without live API access?"). Answer one of them.
2. **A mechanism beats an opinion.** "We hit X when Y; what fixed it was Z" is a comment. "Great
   point, this is the future" is noise.
3. **Specific and checkable.** One number from your facts, one concrete example. Nothing you would
   not say to the same person face to face with your facts file open.
4. **Complement, don't fight.** The author built or backed something. Show where your angle sits
   *beside* it ("this covers the live tables; the part we kept hitting is the history that only
   exists in old exports"). Never "we do this better".
5. **End with a question or a concrete offer** — something the author can reply to in one line.

## What gets ignored (or hidden)
- Praise, agreement, emoji-only, "+1", "great post", "so true".
- Pitch phrases: "check out", "DM me", "book a demo", "sign up", "our product".
- The product named more than once; a link nobody asked for; hashtags.
- A comment longer than the post. 80–180 words; LinkedIn shows about the first 2–3 lines, so the
  first sentence must carry the point.
- Posting the same comment in several threads. Every comment is written for its thread.

## Which threads
- **Who:** an investor on your target list, a partner at a fund that backs your space, an operator
  your buyer listens to, a founder of an adjacent product (their investors read their threads).
- **When:** inside the window (default 21 days); the first 24–48 hours of a post are when a
  comment is still read by the author.
- **What:** a live question you can answer from experience. No open question → nothing to add →
  skip it, however big the thread.
- A few considered comments a week beat a feed of them. The routine's `max_per_run` is the cap.

## After posting
- Check for replies two days later (the comment note's `check_replies` date). Reply to every
  reply; that is where the conversation becomes a DM, an intro or a meeting.
- When it does, record it — `ledger.py` on the target, an outcome in memory. Which threads and
  which kinds of comment led somewhere is what the next run uses.

## `profile/engage.md` — what to look for (the founder's file)

```markdown
---
type: fundraising-profile
title: Engage
topics: [agent memory, company knowledge graph, context engineering, local-first AI]
adjacent: [Northwind Graph, Meridian Memory]
people: [Jane Doe]
platforms: [linkedin, x, hn, reddit]
window_days: 21
max_per_run: 5
max_comment_chars: 1200
---
# Engage

Topics are the phrases your buyers and investors argue about — not your product's name.
Adjacent products are the ones whose threads your investors already read.
People are the ones whose threads you most want to be useful in.
```
