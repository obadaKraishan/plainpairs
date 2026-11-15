# Removal requests

Anyone, a company whose label is in PlainPairs or anyone else, may ask that a text be taken
out. Open a **Removal request** on the repository's issue page
(<https://github.com/obadaKraishan/plainpairs/issues/new/choose>) and give:

- the label's **set id**, or the NCI summary page's **address**;
- **who is asking** (a name or an organization, and its role);
- **why** (for example, a copyright claim, an error, or a withdrawn label).

## What happens
1. **Within 14 days** the request is answered on the issue.
2. If the text is to be taken out, a line is added to the takedown list, `data/takedown.csv`
   (`kind` is `set_id` or `url`, then `id`, the day it was `received` and a short `reason`).
   The list is public; it names no person.
3. **The next version** leaves out every text row of that label or page: `plainpairs release
   build` reads the takedown list and writes no text row for an entry on it. The **record
   row stays** (identifiers, dates, hashes and measures, no text), so earlier work that used it
   can still be checked. The manifest of each version counts the rows taken down.
4. Earlier versions already published are not changed; a request that needs one changed is
   answered on the issue, and the maintainer decides.

The release check fails if a text row of an entry on the list is in a pack.
