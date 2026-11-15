# Sources and their terms

Read on 2026-11-15. Every quote below is copied from a page saved that day and is listed in
[`quotes.csv`](quotes.csv); `plainpairs quotes-check` confirms each one word for word on the
saved copy (64 of 64 on 2026-11-15). Quote marks and dashes are written plainly here; the check
ignores that difference. This is a reading of public terms for the maintainer's
decision, not legal advice.

## 1. openFDA drug labels (the source)

### Terms of service (<https://open.fda.gov/terms/>)
- **Public domain, with an exception for works FDA does not own.**
  > Unless otherwise noted, the content, data, documentation, code, and related materials on
  > openFDA is public domain and made available with a Creative Commons CC0 1.0 Universal
  > dedication.

  > Some data on openFDA may not be public domain, such as copies of copyrightable works made
  > available to the FDA by private entities. FDA may make these works available under the fair
  > use provision of the Copyright Act or as a result of regulatory directives. Therefore, your
  > rights to use those works may be similarly limited.

  > Works where CC0 do not apply will be clearly marked by a warning in the relevant
  > documentation (for example: "This data is not in the public domain. Third party copy rights
  > may apply.").
- **Credit, asked for but not required.**
  > While not required, when using content, data, documentation, code, and related materials
  > from openFDA in your own work, we ask that proper credit be given. An example citation is
  > provided below:

  > Data provided by the U.S. Food and Drug Administration (https://open.fda.gov)
- **Limits.**
  > If FDA reasonably believes that you have attempted to exceed or circumvent these limits, your
  > ability to use openFDA may be temporarily or permanently restricted.
- **No warranty.**
  > FDA makes no warranty that openFDA data will be error free or that access thereto will be
  > continuous or uninterrupted.

### License page (<https://open.fda.gov/license/>, "Last modified: May 27, 2014")
- **No implied endorsement.**
  > When using or citing the work, you should not imply endorsement by the author or the
  > affirmer.
- **Exemptions.** The page promises to list data outside CC0, and lists none:
  > In the future, if we post data that may not be covered under the terms listed above, we will
  > specify the data (or specifc fields inside a dataset) that is not covered and the copyright
  > status of that work here.

### Is the label data "clearly marked"?
No such warning appears on any page saved for the label data: the dataset page, the label API
overview, the how-to page, the field list (page and YAML), the downloads page and
`download.json`. The dataset page gives the license as:
> Public Domain and CC0

Yet the texts are written by companies (section 4), and in the sample part 89 of the 787 labels
with a Medication Guide or a patient package insert (11.3%) carry a copyright mark (the sign,
the word or "all rights reserved") somewhere in their text: in 38 Medication Guides, 35 patient
package inserts, 26 instructions for use and 43 patient counseling sections. The corpus would
need to treat that text with care whatever the dataset page says (decision for the maintainer).

### The dataset and the API
- **What it is.**
  > Drug manufacturers and distributors submit documentation about their products to FDA.

  > openFDA annotates the original records with special fields and converts the data into JSON,
  > which is a widely used machine readable format.
- **Time covered and updates.** "Frequency Weekly" (dataset page), and:
  > The bulk of the data is from June 2009 (when labeling was first posted publicly in the SPL
  > format) to the present. However, there are a small number of records from earlier than
  > mid-2009.
- **The disclaimer the source asks for** (label API page; `download.json` repeats its first
  sentence and adds "you should assume all results are unvalidated"):
  > Do not rely on openFDA to make decisions regarding medical care. Always speak to your health
  > provider about the risks and benefits of FDA-regulated products.

  > The drug labels and other drug-specific information provided in this API represent the most
  > recent drug listing information companies have submitted to the Food and Drug
  > Administration (FDA). (See 21 CFR part 207.) The drug labeling and other information has
  > been reformatted to make it easier to read but its content has neither been altered nor
  > verified by FDA. The drug labeling provided in this API may not be the labeling on currently
  > distributed products or identical to the labeling that is approved.
- **Only the latest version of each label.** "the most recent drug listing information" above,
  and the sample part holds exactly one record per set id (4,748 of 4,748). The field list
  defines `set_id` as:
  > The Set ID, A globally unique identifier (GUID) for the labeling, stable across all versions
  > or revisions.
- **Limits** (<https://open.fda.gov/apis/authentication/>). The page says both:
  > An API key is required to make calls to the openFDA API.

  > With no API key: 240 requests per minute, per IP address. 1,000 requests per day, per IP
  > address.

  > With an API key: 240 requests per minute, per key. 120,000 requests per day, per key.

  This session used no key: 70 calls to api.fda.gov (68 counts, and `download.json` with its
  HEAD) and one bulk download, one at a time and at least 1 s apart. None answered 429 or 5xx. A count may return at most 1,000 values: "The maximum limit
  allowed is 1000 for any single API call."
- **Bulk files** (<https://open.fda.gov/apis/downloads/>): 14 zipped JSON parts for drug labels,
  listed in `download.json` (sizes in `docs/backfill.md`). An update can touch every record:
  > Every time an endpoint is updated (which happens on a regular basis), it is possible that
  > every record has changed, due to corrections or enhancements. That means that you cannot
  > simply download "new" files to keep your downloaded version up to date. You need to download
  > all available data files for the endpoint of interest.
- **Patient fields**, as the field list defines them (it has no field for section 17, "Patient
  Counseling Information"; the sample shows that section stored in `information_for_patients`):
  - `spl_medguide`: "Information about the patient medication guide that accompanies the drug
    product. Certain drugs must be dispensed with an accompanying medication guide."
  - `information_for_patients`: "Information necessary for patients to use the drug safely and
    effectively, such as precautions concerning driving or the concomitant use of other
    substances that may have harmful additive effects."
  - `patient_medication_information`: "Information or instructions to patients about safe use of
    the drug product, sometimes including a reference to a patient medication guide or
    counseling materials."
- **The NDC directory** (for the "listed now" flag). openFDA's `drug/ndc` bulk file, as
  `download.json` lists it: one part, 26.94 MiB, 138,372 records, export of 2026-11-13. It falls
  under the same openFDA terms as the label data (above). Only each entry's `spl_id` and
  `openfda.spl_set_id` are read, to say whether a label's product is in the current directory.

## 2. DailyMed (National Library of Medicine)
- **Who writes the labels, and who checks them** (<https://dailymed.nlm.nih.gov/dailymed/about-dailymed.cfm>):
  > The DailyMed database contains labeling, submitted to the Food and Drug Administration (FDA)
  > by companies, for the following products:

  > The labeling on DailyMed is the most recent submitted labeling to the FDA by companies and
  > currently in use (i.e., "in use" labeling).

  > The contents of the "in use" labeling on DailyMed may not have been verified by FDA. Note:
  > NLM does not review any SPL content prior to publication.
- **Reuse.** DailyMed's own pages say nothing about reuse; its footer's "Copyright" link leads to
  NLM's web policy (<https://www.nlm.nih.gov/web_policies.html>):
  > Works produced by the U.S. government are not subject to copyright protection in the United
  > States.

  > When using NLM Web sites, you may encounter documents, illustrations, photographs, or other
  > content contributed by or licensed from private individuals, companies, or organizations
  > that may be protected by U.S. and international copyright laws.

  > However, a copyright notice is not required by law and therefore not all copyrighted content
  > is necessarily marked in this way.

  > It is your responsibility to determine and satisfy copyright or other use restrictions when
  > using materials that are not in the public domain. NLM cannot guarantee the copyright status
  > for any item.

  The credit NLM asks for its own works:
  > Please acknowledge NLM as the source of the information by including the phrase "Courtesy of
  > the National Library of Medicine" or "Source: National Library of Medicine."
- **Older versions.** DailyMed keeps them, which openFDA does not:
  > This archive allows the user to retrieve the label current for a given date.

  (<https://dailymed.nlm.nih.gov/dailymed/archives/index.cfm>), and its web service
  `/spls/{SETID}/history` "Returns version history for the specified SET ID." DailyMed also
  offers SPL XML downloads, which keep the section structure that openFDA's JSON flattens: full
  releases in parts (human prescription labels: 6 parts, 55,148 files, about 16.8 GB) and
  daily, weekly and monthly updates (October 2026: 4,131 labels, 1.67 GB).
  > Warning: The full human prescription and OTC archive files, dm_spl_release_human_rx.zip and
  > dm_spl_release_human_otc.zip, are no longer available due to size considerations.
- **Labels DailyMed no longer serves** (checked 2026-11-15). The archive page
  (<https://dailymed.nlm.nih.gov/dailymed/archives/index.cfm>) says:
  > This archive allows the user to retrieve the label current for a given date. By default,
  > only archived labels for this year are returned.

  > If you wish to request all labels for a given date, please visit our customer support.

  For one of the seven labels that DailyMed's single-label service answered with 404 in the
  20-label test (`docs/xml-test.md`), the history service (`/spls/{SETID}/history.json`) still
  lists both of its versions (with no title), and an archive search by its set id finds both,
  each with a download link. That link (`/dailymed/getArchivalFile.cfm?archive_id=...`)
  answers with `application/zip`, a file named `<date>_<set id>.zip`: the same form as the
  per-label zips inside the full release (one SPL XML document and its images). The version
  the corpus holds is one of the two. So the archive does keep labels DailyMed no longer
  serves, as SPL XML, one version at a time. Nothing was downloaded from it: one request per
  label is not a reasonable load for the labels concerned, and the bulk route the page names
  goes through customer support, which this project has not contacted. Four requests were
  made for this check: the help page, the history answer, the archive search and the headers
  of one archive file (no body).
- **The list of labels DailyMed serves** (for the "listed now" flag). The zip file metadata,
  `dm_spl_zip_files_meta_data.zip` (7.30 MB as listed, MD5 as listed, last modified
  2026-11-13), on the mapping files page
  (<https://dailymed.nlm.nih.gov/dailymed/spl-resources-all-mapping-files.cfm>):
  > These files map SPL Set ID to other information.

  and described on the application support page
  (<https://dailymed.nlm.nih.gov/dailymed/app-support-mapping-files.cfm>):
  > This file maps SPL Set IDs to their zip file name and drug title. For each SPL zip file name,
  > there will be one and only entry in this file.

  Neither page states terms of reuse; NLM's web policy (above) applies, and the file is NLM's
  own index. Only the set id and the version are read; the titles are never kept, and the file
  is not redistributed.

## 3. FDA's website policy (<https://www.fda.gov/about-fda/about-website/website-policies>)
> Unless otherwise noted, the contents of the FDA website (www.fda.gov) - both text and
> graphics - are not copyrighted. They are in the public domain and may be republished,
> reprinted and otherwise used freely by anyone without the need to obtain permission from FDA.

> If a person, nonetheless, decides to copy content or images, FDA strongly recommends that the
> copied item lists the date that the material was copied and provides a link back to its
> source on the FDA website.

Whether "the contents of the FDA website" covers company-written labeling that FDA republishes
is not stated.

## 4. Who holds rights in label text
Companies write labels; FDA approves the prescription labels it reviews and republishes them;
NLM republishes them without review. What the pages read say:

- **FDA (openFDA):** CC0 "unless otherwise noted", but "copies of copyrightable works made
  available to the FDA by private entities" may not be public domain, and such works "will be
  clearly marked". The label data are not marked.
- **NLM:** company-contributed content "may be protected", unmarked content may still be
  copyrighted, and "NLM cannot guarantee the copyright status for any item."
- **The one appellate ruling found:** *SmithKline Beecham Consumer Healthcare, L.P. v. Watson
  Pharmaceuticals, Inc.*, 211 F.3d 21 (2d Cir. 2000), read in the reprint at
  <https://biotech.law.lsu.edu/cases/devices/smithkline_v_watson.htm> (CourtListener's copy did
  not load):
  > We hold that the Hatch-Waxman Amendments to the Federal Food, Drug, and Cosmetic Act require
  > generic drug sellers to use labeling that may infringe a copyright in the label of the
  > pioneer drug. We further hold that, as a result, copyright liability cannot attach to
  > Watson's use of SmithKline's label.

  > SmithKline's copyright claim is therefore meritless, and we need not address either the
  > fair use or implied license defenses.

  The court says the brand owner
  > still retains a copyright, if otherwise valid, in the label and might well pursue copyright
  > claims against potential infringers in other circumstances, e.g., use of the copyrighted
  > material in non-labeling advertisements.

  and reports FDA's position that it had
  > never been directed by Congress to consider potential copyright rights in approving generic
  > drug labeling.
- **Federal Register:** no statement on copyright in labeling was found in the Medication Guide
  rule (63 FR 66378, 1998), the prescribing-information format rule (71 FR 3922, 2006) or the
  PMI proposed rule (88 FR 35694, 2023). The 1992 generic-drug rule (57 FR 17950) was not read.

**What is settled:** openFDA's terms dedicate its own work to the public domain and do not mark
the label data as an exception; generic makers may copy brand labeling because the law requires
them to.

**What is not settled:** whether the companies that wrote the labels hold copyright in the text,
whether a research corpus that redistributes it (with measures added) would be fair use, and
whether FDA-written text inside labels (class labeling, templates) is a government work. The
ruling covers only copying the law requires; a research corpus is not that. No ruling on
Medication Guides, patient package inserts or a non-generic reuse of label text was found. This
is the maintainer's decision; it is not settled here by assumption.

## 5. National Cancer Institute (a possible second source; nothing crawled)
- **Text** (<https://www.cancer.gov/policies/copyright-reuse>):
  > Unless otherwise indicated, all text within National Cancer Institute (NCI) products is free
  > of copyright and may be reused without our permission. Credit the National Cancer Institute
  > as the source.
- **The PDQ name:**
  > The NCI logo and the PDQ trademark may only be used in reproductions of original, wholly
  > unchanged NCI products.

  A corpus that cleans, splits or measures the summaries is changed, so it may not carry the PDQ
  name or logo; translations "may not use the NCI logo or PDQ trademark".
- **Graphics:**
  > Graphics (photos, illustrations) used in National Cancer Institute (NCI) information products
  > are a mix of copyrighted and copyright-free materials.
- **Syndication** (<https://www.cancer.gov/syndication>): RSS feeds, a dictionary widget and the
  clinical trials API. "Some of the information on this website is available for use on your own
  site or in other information products." No summary feed or summary API is offered there.
- **robots.txt:** `User-agent: *` with no `Disallow` line, and a sitemap.
- **What the summaries are** (<https://www.cancer.gov/publications/pdq/information-summaries>):
  > Most of the health professional summaries are also available in a patient-focused format.

  > They are not clinical practice guidelines or treatment recommendations and are not intended
  > to be used as a basis for insurance reimbursement.
- **How many**, from the sitemap (`sitemaps/pageinstructions.xml`, 6,457 URLs, one request), as
  page URLs ending in `-pdq` (pages, not a checked list of summaries):

  | language | health professional | patient |
  |---|---:|---:|
  | English | 237 | 152 |
  | Spanish | 215 | 152 |

### Are the summaries distributed as files? (checked 2026-11-15)
Not on NCI's own pages. The PDQ content partners page
(<https://www.cancer.gov/publications/pdq/content-partners>, "Posted: November 19, 2024") says
of its content distribution partners:
> These partners use NCI-produced content in their websites and information products and may
> syndicate it to their partners and customers, further extending its dissemination.

> The summaries are made available to these partners through the NCI content syndication
> program.

Its link to that program (`/node/13430`) answered 404 on 2026-11-15, and NCI's syndication page
(<https://www.cancer.gov/syndication>) offers RSS feeds, a dictionary widget and the clinical
trials API, with no summary files or summary feed. The same page lists NCBI Bookshelf (National
Library of Medicine) among the partners, and says "Almost all PDQ health professional and
patient summaries, as well as other NCI content, are available in Spanish from NCI." So a public
file download of the summaries was not found; S3 has three routes: the web pages themselves
(about 760 pages in the sitemap, which is a crawl and needs the maintainer's approval), the
partner copy on NCBI Bookshelf (terms not yet read), or asking NCI about the syndication program
(contact is the maintainer's to make). Nothing was crawled.

## 6. Codebook instruments
- **PEMAT (AHRQ).** The PEMAT page and AHRQ's copyright policy answered 403 to automated reads.
  The maintainer's own copies of the printable form (PEMAT-P) and the user's guide (Version 1.0,
  November 2013, updated August 2014; AHRQ Publication No. 14-0002-EF) were read: neither states
  terms of reuse. So the codebook (`docs/codebook.md`) names each PEMAT-P item it draws on by
  its number and topic only, describes it in this project's words, cites the guide, and
  reprints nothing; its measures are "PEMAT-informed text items", not PEMAT scores. Citations:
  Shoemaker SJ, Wolf MS, Brach C. *The Patient Education Materials Assessment Tool (PEMAT) and
  User's Guide.* Rockville, MD: Agency for Healthcare Research and Quality; 2013. AHRQ Publication
  No. 14-0002-EF; and Shoemaker SJ, Wolf MS, Brach C. Development of the Patient Education
  Materials Assessment Tool (PEMAT): a new measure of understandability and actionability for
  print and audiovisual patient information. *Patient Educ Couns.* 2014;96(3):395-403.
- **CDC Clear Communication Index** (<https://www.cdc.gov/ccindex/index.html>):
  > The Index has 4 introductory questions and 20 scored items drawn from scientific literature
  > in communication and related disciplines.

  CDC's policy for its materials (<https://www.cdc.gov/other/agencymaterials.html>):
  > Most of the information on the CDC and ATSDR websites is not subject to copyright, is in the
  > public domain, and may be freely used or reproduced without obtaining copyright permission.

  with four conditions:
  > 1) Attribution to the agency that developed the material must be provided in your use of the
  > materials.

  > 2) You must utilize a disclaimer which clearly indicates that your use of the material,
  > including any links to the materials on the CDC, ATSDR or HHS websites, does not imply
  > endorsement by CDC, ATSDR, HHS or the United States Government of you, your company,
  > product, facility, service or enterprise.

  > 3) You may not change the substantive content of the materials; and

  > 4) You must state that the material is otherwise available on the agency website for no
  > charge.

  So the items may be reprinted with credit, the disclaimer and a pointer to CDC's site, but not
  reworded; a codebook that adapts them should describe the adaptation and cite them rather than
  present reworded items as CDC's. Citation: Baur C, Prue C. The CDC Clear Communication Index is
  a new evidence-based tool to prepare and review health information. *Health Promot Pract.*
  2014;15(5):629-637.

## 7. The Patient Medication Information rule
The proposed rule (88 FR 35694, 2023-05-31, RIN 0910-AH68) would create a one-page Patient
Medication Information that "would replace current Medication Guides and Patient Package
Inserts" (FDA's PMI page). Its status on 2026-11-15:
> The comment period on the proposed rule closed on November 27, 2023. FDA is in the process of
> reviewing the comments for consideration in issuing a final rule.

The Unified Agenda lists it at "Final Rule Stage" with a final rule planned for "12/00/2026". No
final rule has been published. The source field `patient_medication_information` is a different
thing: SPL section code 68498-5, "PATIENT MEDICATION INFORMATION SECTION", in FDA's list of
section headings. It is used on 1,380 labels with effective dates from 2005 to 2026, and in the
sample its 24 texts are a mix of patient information leaflets, Medication Guides, consumer
information and section 17 text. It is not the format the rule proposes.

## 8. Names
The project's name is PlainPairs. "FDA", "openFDA", "DailyMed", "NCI", "PDQ" and "MedlinePlus"
are used only to say where data come from, never in a name or in a way that suggests
endorsement. What each asks of reusers:

| source | credit asked | other conditions |
|---|---|---|
| openFDA | "Data provided by the U.S. Food and Drug Administration (https://open.fda.gov)" (asked, not required) | no implied endorsement; the medical-care disclaimer |
| FDA website | credit "appreciated but not required" | date copied and a link back |
| NLM / DailyMed | "Courtesy of the National Library of Medicine" or "Source: National Library of Medicine" (for NLM's own works) | the user checks the status of non-government content |
| NCI | "Credit the National Cancer Institute as the source" | no NCI logo or PDQ name on changed products; graphics may be copyrighted |
| CDC | attribution to CDC | a non-endorsement disclaimer; no change to substantive content; say it is free on CDC's site |
