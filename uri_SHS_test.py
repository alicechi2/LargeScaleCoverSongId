#!/usr/bin/env python
"""
Test with meanAP and average rank
"""


import os
import sys
import cPickle
import pickle
import numpy as np
import argparse
from scipy.spatial import distance
import time
import glob
# local stuff
import pca
import hdf5_getters as GETTERS
import dan_tools
import time
import utils
import scipy.cluster.vq as vq
import pylab as plt
from transforms import load_transform
import analyze_stats as anst

# params, for ICMR paper: 75 and 1.96
WIN = 75
PATCH_LEN = WIN*12

def print_verbose(verb, string):
    """Print string if verb is true."""
    if verb:
        print string

def compute_codes_it(track_ids, maindir, d, clique_ids, lda, 
        start_idx, end_idx):
    fx = load_transform(d)
    K = int(d.split("_")[1].split("E")[1])
    res = []
    lda_components = [50,100,200]

    # Init codes
    codes = []
    for n_comp in lda_components:
        codes.append(np.ones((end_idx-start_idx,n_comp)) * np.nan)

    for i, tid in enumerate(track_ids[start_idx:end_idx]):
        path = utils.path_from_tid(maindir, tid)
        feats = utils.extract_feats(path)
        if feats == None:
            continue
        med = np.median(fx(feats), axis=0)
        for lda_idx, n_comp in enumerate(lda_components):
            tmp = lda[lda_idx].transform(med)
            codes[lda_idx][i] = dan_tools.chromnorm(tmp.reshape(tmp.shape[0], 
                                    1)).squeeze()
        if i % 1000 == 0:
            print "Computed %d of %d track(s)" % (i, end_idx-start_idx)
    res = (codes, track_ids[start_idx:end_idx], clique_ids[start_idx:end_idx])
    return res

def compute_codes(track_ids, maindir, d, N, clique_ids, lda):
    """Computes maximum 10,000 x 10 tracks. N is the index in the MSD:
        e.g. 
            if N = 1: tracks computed: from 100,000 to 199,999
            if N = 5: tracks computed: from 500,000 to 599,999
    """
    for it in xrange(10):
        print "Computing %d of 10 iteration" % it
        start_idx = int(N*1e5 + it*1e4)
        end_idx = int(start_idx + 1e4)
        print start_idx, end_idx
        codes = compute_codes_it(track_ids, maindir, d, clique_ids, lda,
            start_idx, end_idx)
        out_file = "msd_codes/" + str(N) + str(it) + "-msd-codes.pk"
        f = open(out_file, "w")
        cPickle.dump(codes, f, protocol=1)
        f.close()

def load_codes(codesdir, lda_idx):
    code_files = glob.glob(os.path.join(codesdir, "*.pk"))
    if lda_idx == 0:
        n_comp = 50
    elif lda_idx == 1:
        n_comp = 100
    elif lda_idx == 2:
        n_comp = 200
    feats = np.empty((0,n_comp))
    track_ids = []
    clique_ids = []
    for code_file in code_files:
        codes = utils.load_pickle(code_file)
        feats = np.append(feats, codes[0][lda_idx], axis=0)
        track_ids += codes[1]
        clique_ids += codes[2]

    track_ids = np.asarray(track_ids)
    clique_ids = np.asarray(clique_ids)
    print feats.shape, track_ids.shape, clique_ids.shape

    f = open("msd_codes_" + str(n_comp) + ".pk", "w")
    cPickle.dump((feats,track_ids,clique_ids), f, protocol=1)
    f.close()

    return feats, track_ids, clique_ids

def score(feats, clique_ids, lda_idx=0):
    stats = [np.inf] * 5236
    #stats = [np.inf] * 12960
    #stats = [np.inf]*len(feats)
    
    # For each track id that has a clique id
    print "Computing scores for the MSD..."
    q = 0
    for i, clique_id in enumerate(clique_ids):
        if clique_id == -1:
            continue
        D = distance.cdist(feats[i][np.newaxis,:], feats, metric="euclidean")
        s = np.argsort(D)[0]
        sorted_cliques = clique_ids[s]
        r = np.argwhere( sorted_cliques == clique_id )[1:]
        if len(r) > 0:
            stats[q] = r
        q += 1
        if q % 400 == 0:
            print 'After %d queries: average rank per track: %.2f, clique: %.2f, MAP: %.5f' \
                % (q, anst.average_rank_per_track(stats),
                    anst.average_rank_per_clique(stats),
                    anst.mean_average_precision(stats, n=1e6))

    return stats


def main():
    # Args parser
    parser = argparse.ArgumentParser(description=
                "Evaluates the average rank and mean AP for the test SHS")
    parser.add_argument("-d", dest="dictfile", action="store", default="",
                        help="Pickle to the learned dictionary")
    parser.add_argument("-N", action="store", type=int, default=0,
                        help="Set of 100,000ths to be computed")
    parser.add_argument("-v", action="store_true", default=False,
                        help="Verbose mode")  
    parser.add_argument("-lda", action="store", default=None, 
                        help="LDA file")
    parser.add_argument("-codes", action="store", default=None, dest="codesdir",
                        help="Path to the folder with all the codes")

    args = parser.parse_args()
    start_time = time.time()
    maindir = "/Volumes/MyBook/datasets/MSD/uncompressedData"
    shsf = "SHS/shs_dataset_test.txt"

    # sanity cheks
    utils.assert_file(maindir)
    utils.assert_file(shsf)

    # read cliques and all tracks
    cliques, all_tracks = utils.read_shs_file(shsf)

    # read LDA file
    lda_file = args.lda
    if lda_file != None:
        lda_file = utils.load_pickle(lda_file)
        print "LDA file read"

    # read codes file
    codesdir = args.codesdir
    if codesdir != None:
        #feats, track_ids, clique_ids = load_codes(codesdir, lda_idx=2)
        c = utils.load_pickle(codesdir)
        feats = c[0]
        track_ids = c[1]
        clique_ids = c[2]
        print "Codes files read"
    else:
        utils.assert_file(args.dictfile)
        track_ids = utils.load_pickle("track_ids_msd.pk")
        clique_ids = utils.load_pickle("clique_ids_msd.pk")
        compute_codes(track_ids, maindir, args.dictfile, args.N, clique_ids, 
            lda_file)
        print "Codes computation done!"
        print "Took %.2f seconds" % (time.time() - start_time)
        sys.exit()

    # Scores
    feats, clique_ids, track_ids = utils.clean_feats(feats, clique_ids, track_ids)
    stats = score(feats, clique_ids)

    f = open("stats-" + os.path.basename(args.dictfile), "w")
    cPickle.dump(stats, f, protocol=1)
    f.close()

    # done
    print 'DONE!'
    print 'Average rank per track: %.2f, clique: %.2f, MAP: %.5f' \
                % (anst.average_rank_per_track(stats),
                    anst.average_rank_per_clique(stats),
                    anst.mean_average_precision(stats, n=1e6))
    print "Took %.2f seconds" % (time.time() - start_time)

if __name__ == '__main__':
    main()