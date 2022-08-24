###
# Taken from unassigner
# https://github.com/kylebittinger/unassigner
###

import collections
import logging
import os
import shutil
import subprocess
import urllib.request
from io import StringIO

### from unassigner.parse import parse_fasta, parse_greengenes_accessions ###
def parse_fasta(f, trim_desc=False):
    """Parse a FASTA format file.
    Parameters
    ----------
    f : File object or iterator returning lines in FASTA format.
    Returns
    -------
    An iterator of tuples containing two strings
        First string is the sequence description, second is the
        sequence.
    Notes
    -----
    This function removes whitespace in the sequence and translates
    "U" to "T", in order to accommodate FASTA files downloaded from
    SILVA and the Living Tree Project.
    """
    f = iter(f)
    try:
        desc = next(f).strip()[1:]
        if trim_desc:
            desc = desc.split()[0]
    except StopIteration:
        return
    seq = StringIO()
    for line in f:
        line = line.strip()
        if line.startswith(">"):
            yield desc, seq.getvalue()
            desc = line[1:]
            if trim_desc:
                desc = desc.split()[0]
            seq = StringIO()
        else:
            seq.write(line.replace(" ", "").replace("U", "T"))
    yield desc, seq.getvalue()

def parse_greengenes_accessions(f):
    for line in f:
        if line.startswith("#"):
            continue
        line = line.strip()
        yield line.split("\t")
###

LTP_METADATA_COLS = [
    "accession",
    "start",
    "stop",
    "unknown",
    "fullname_ltp",
    "type_ltp",
    "hi_tax_ltp",
    "riskgroup_ltp",
    "url_lpsn_ltp",
    "tax_ltp",
    "rel_ltp",
    "NJ_support_pk4_ltp"
    ]
LTP_METADATA_URL = \
    "https://imedea.uib-csic.es/mmg/ltp/wp-content/uploads/ltp/LTP_09_2021.csv"
LTP_SEQS_URL = \
    "https://imedea.uib-csic.es/mmg/ltp/wp-content/uploads/ltp/LTP_09_2021_blastdb.fasta"
GG_SEQS_URL = \
    "ftp://greengenes.microbio.me/greengenes_release/gg_13_5/gg_13_5.fasta.gz"
GG_ACCESSIONS_URL = \
    "ftp://greengenes.microbio.me/greengenes_release/gg_13_5/gg_13_5_accessions.txt.gz"
SPECIES_FASTA_FP = "type_species.fasta"
REFSEQS_FASTA_FP = "refseqs.fasta"
GG_DUPLICATE_FP = "gg_duplicate_ids.txt"

def clean(db_dir):
    fps = [
        url_fp(LTP_METADATA_URL),
        url_fp(LTP_SEQS_URL),
        SPECIES_FASTA_FP,
        gunzip_fp(url_fp(GG_SEQS_URL)),
        gunzip_fp(url_fp(GG_ACCESSIONS_URL)),
        REFSEQS_FASTA_FP,
        GG_DUPLICATE_FP
        ]
    for fp in fps:
        fp_full = os.path.join(db_dir, fp)
        if os.path.exists(fp_full):
            os.remove(fp_full)


def url_fp(url):
    return url.split('/')[-1]


def gunzip_fp(fp):
    return fp[:-3]

def get_url(url, fp):
    logging.info("Downloading {0}".format(url))
    with urllib.request.urlopen(url) as resp, open(fp, 'wb') as f:
        shutil.copyfileobj(resp, f)
    return fp


def process_ltp_seqs(input_fp, output_fp=SPECIES_FASTA_FP):
    if os.path.isdir(output_fp):
        output_fp = os.path.join(output_fp, SPECIES_FASTA_FP)
    accession_cts = collections.defaultdict(int)
    # Re-format FASTA file
    with open(input_fp) as f_in:
        seqs = parse_fasta(f_in)
        with open(output_fp, "w") as f_out:
            for desc, seq in seqs:
                vals = desc.split("|")
                # Some accessions refer to genomes with more than one 16S gene
                # So accessions can be legitiamtely repeated with distinct gene sequences
                accession = vals[2]
                accession_times_previously_seen = accession_cts[accession]
                accession_cts[accession] += 1
                if accession_times_previously_seen > 0:
                    accession = "{0}_repeat{1}".format(accession, accession_times_previously_seen)
                species_name = vals[3]
                f_out.write(
                    ">{0}\t{1}\n{2}\n".format(accession, species_name, seq))
    return output_fp


def process_greengenes_seqs(seqs_fp, accessions_fp, output_fp=REFSEQS_FASTA_FP):
    duplicates_fp = GG_DUPLICATE_FP
    if os.path.isdir(output_fp):
        duplicates_fp = os.path.join(output_fp, duplicates_fp)
        output_fp = os.path.join(output_fp, REFSEQS_FASTA_FP)

    # Extract table of accessions
    if accessions_fp.endswith(".gz"):
        subprocess.check_call(["gunzip", "-f", accessions_fp])
        accessions_fp = gunzip_fp(accessions_fp)

    # Load accessions
    gg_accessions = {}
    with open(accessions_fp) as f:
        for ggid, src, acc in parse_greengenes_accessions(f):
            gg_accessions[ggid] = (acc, src)

    # Extract FASTA file
    if seqs_fp.endswith(".gz"):
        subprocess.check_call(["gunzip", "-f", seqs_fp])
        seqs_fp = gunzip_fp(seqs_fp)

    # Remove duplicate reference seqs
    uniq_seqs = collections.defaultdict(list)
    with open(seqs_fp) as f:
        for ggid, seq in parse_fasta(f):
            uniq_seqs[seq].append(ggid)

    with open(duplicates_fp, "w") as dups:
        with open(output_fp, "w") as f:
            for seq, ggids in uniq_seqs.items():
                ggid = ggids[0]
                if len(ggids) > 1:
                    dups.write(" ".join(ggids))
                # Re-label seqs with accession numbers
                acc, src = gg_accessions[ggid]
                f.write(">%s %s %s\n%s\n" % (acc, src, ggid, seq))

    return output_fp