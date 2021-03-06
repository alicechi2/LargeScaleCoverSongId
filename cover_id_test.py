#!/usr/bin/env python
"""


----
Authors: 
Uri Nieto (oriol@nyu.edu)
Eric J. Humphrey (ejhumphrey@nyu.edu)

----
License:
This code is distributed under the GNU LESSER PUBLIC LICENSE 
(LGPL, see www.gnu.org).

Copyright (c) 2012-2013 MARL@NYU.
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

  a. Redistributions of source code must retain the above copyright notice,
     this list of conditions and the following disclaimer.
  b. Redistributions in binary form must reproduce the above copyright
     notice, this list of conditions and the following disclaimer in the
     documentation and/or other materials provided with the distribution.
  c. Neither the name of MARL, NYU nor the names of its contributors
     may be used to endorse or promote products derived from this software
     without specific prior written permission.


THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE REGENTS OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH
DAMAGE.
"""


import os
import sys
import cPickle
import pickle
import numpy as np
import argparse
from scipy.spatial import distance
from multiprocessing import Pool
import time
import glob

# local stuff
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

# Set up logger
logger = utils.configure_logger()

# Global models
lda = None
pca = None

def compute_codes_orig_it(track_ids, maindir, clique_ids, start_idx, end_idx):
    """Computes the original features, based on Thierry and Ellis, 2012.
    Dimensionality reduction using PCA of 50, 100, and 200 components."""
    res = []
    trainedpca = utils.load_pickle("models/pca_250Kexamples_900dim_nocovers.pkl")
    pca_components = [50,100,200]

    # Init codes
    codes = []
    for n_comp in pca_components:
        codes.append(np.ones((end_idx-start_idx,n_comp)) * np.nan)

    for i, tid in enumerate(track_ids[start_idx:end_idx]):
        path = utils.path_from_tid(maindir, tid)
        feats = utils.extract_feats(path)
        if feats == None:
            continue
        med = np.median(feats, axis=0)
        for pca_idx, n_comp in enumerate(pca_components):
            tmp = dan_tools.chromnorm(med.reshape(med.shape[0], 
                                    1)).squeeze()
            codes[pca_idx][i] = trainedpca.apply_newdata(tmp, ndims=n_comp)
        if i % 1000 == 0:
            logger.info("Computed %d of %d track(s)" % (i, end_idx-start_idx))
    res = (codes, track_ids[start_idx:end_idx], clique_ids[start_idx:end_idx])
    return res

def compute_codes_it(track_ids, maindir, d, clique_ids, 
        start_idx, end_idx, origcodes=None, norm=False):
    """Computes the features based on Humphrey, Nieto and Bello, 2013.
    Dimensionality reduction using LDA of 50, 100, and 200 components."""
    fx = load_transform(d)
    res = []
    K = int(d.split("_")[1].split("E")[1])

    # Init codes
    codes = []
    if lda is not None:
        lda_components = [50,100,200]
        for n_comp in lda_components:
            codes.append(np.ones((end_idx-start_idx,n_comp)) * np.nan)
    else:
        codes.append(np.ones((end_idx-start_idx, K)) * np.nan)

    for i, tid in enumerate(track_ids[start_idx:end_idx]):
        if origcodes is None:
            path = utils.path_from_tid(maindir, tid)
            feats = utils.extract_feats(path)
            if feats == None:
                continue
            code = np.median(fx(feats), axis=0)
        else:
            code = origcodes[i]
        if norm:
            code = dan_tools.chromnorm(code.reshape(code.shape[0], 
                                        1)).squeeze()
        if pca is not None:
            code = pca.transform(code)
        if lda is not None:
            for lda_idx, n_comp in enumerate(lda_components):
                tmp = lda[lda_idx].transform(code)
                codes[lda_idx][i] = dan_tools.chromnorm(tmp.reshape(tmp.shape[0], 
                                        1)).squeeze()
        else:
            codes[0][i] = code 
        if i % 1000 == 0:
            logger.info("Computed %d of %d track(s)" % (i, end_idx-start_idx))
    res = (codes, track_ids[start_idx:end_idx], clique_ids[start_idx:end_idx])
    return res

def compute_codes(args):
    """Computes maximum 10,000 x 10 tracks. N is the index in the MSD:
        e.g. 
            if N = 1: tracks computed: from 100,000 to 199,999
            if N = 5: tracks computed: from 500,000 to 599,999
    """

    track_ids = args["track_ids"]
    maindir = args["maindir"]
    d = args["d"]
    N = args["N"]
    clique_ids = args["clique_ids"]
    outdir = args["outdir"]
    origcodesdir = args["origcodesdir"]
    pca_n = args["pca_n"]
    norm = args["norm"]

    MAX     = 1e5 / 1
    ITER    = 1e4 / 1

    for it in xrange(10):
        logger.info("Computing %d of 10 iteration" % it)
        start_idx = int(N*MAX + it*ITER)
        end_idx = int(start_idx + ITER)
        codes = []
        strN = str(N)
        if N < 10:
            strN = "0" + str(N)
        out_file = os.path.join(outdir, strN) + str(it) + "-msd-codes.pk"
        if origcodesdir is None:
            origcodes = None
        else:
            origcodes_file = os.path.join(origcodesdir, strN) + str(it) + \
                "-msd-codes.pk"
            origcodes = utils.load_pickle(origcodes_file)[0][0]
            #origcodes = utils.load_pickle(origcodes_file)[0]
        if d == "":
            codes = compute_codes_orig_it(track_ids, maindir, clique_ids,
                start_idx, end_idx)
        else:
            codes = compute_codes_it(track_ids, maindir, d, clique_ids,
                start_idx, end_idx, origcodes=origcodes, norm=norm)
        
        utils.save_pickle(codes, out_file)

def score(feats, clique_ids, N=5236, lda_idx=0):
    stats = [np.inf] * N
    
    # For each track id that has a clique id
    logger.info("Computing scores for the MSD...")
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
            logger.info('After %d queries: average rank per track: %.2f'
                ', clique: %.2f, MAP: %.2f%%' \
                % (q, anst.average_rank_per_track(stats),
                    anst.average_rank_per_clique(stats),
                    anst.mean_average_precision(stats) * 100))

    return stats

def load_codes(codesdir, lda_idx, max_files=None):
    code_files = glob.glob(os.path.join(codesdir, "*.pk"))
    if lda_idx == 0:
        n_comp = 50
    elif lda_idx == 1:
        n_comp = 100
    elif lda_idx == 2:
        n_comp = 200
    elif lda_idx == -1:
        n_comp = 2045
    feats = np.empty((0,n_comp))
    track_ids = []
    clique_ids = []
    if max_files is not None:
        code_files = code_files[:max_files]
    for code_file in code_files:
        codes = utils.load_pickle(code_file)
        feats = np.append(feats, codes[0][lda_idx], axis=0)
        track_ids += codes[1]
        clique_ids += list(codes[2])

    track_ids = np.asarray(track_ids)
    clique_ids = np.asarray(clique_ids)

    return feats, track_ids, clique_ids

def main():
    # Args parser
    parser = argparse.ArgumentParser(description=
                "Evaluates the average rank and mean AP for the test SHS " \
                "over the entire MSD",
                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("msd_dir", action="store",
                        help="Million Song Dataset main directory")
    parser.add_argument("-dictfile", action="store", default="",
                        help="Pickle to the learned dictionary")
    parser.add_argument("-outdir", action="store", default="msd_codes",
                        help="Output directory for the features")
    parser.add_argument("-N", action="store", default=10, type=int,
                        help="Number of processors to use when computing " \
                        "the codes for 1M tracks,")
    parser.add_argument("-lda", action="store", default=None, 
                        help="LDA file")
    parser.add_argument("-pca", nargs=2, metavar=('f.pkl', 'n'), 
                        default=(None, 0),
                        help="pca model saved in a pickle file, " \
                        "use n dimensions")
    parser.add_argument("-codes", action="store", nargs=2, default=[None,0], 
                        dest="codesdir", metavar=("msd_codes/", "n"),
                        help="Path to the folder with all the codes and "
                            "version to evaluate")
    parser.add_argument("-orig_codes", action="store", default=None, 
                        dest="origcodesdir",
                        help="Path to the folder with all the codes without "
                            "dimensionality reduction")
    parser.add_argument("-norm", action="store_true", dest="norm", default=False, 
                        help="Normalize before LDA/PCA or not")

    args = parser.parse_args()
    start_time = time.time()
    maindir = args.msd_dir
    shsf = "SHS/shs_dataset_test.txt"

    global lda
    global pca

    # sanity cheks
    utils.assert_file(maindir)
    utils.assert_file(shsf)
    utils.create_dir(args.outdir)

    # read cliques and all tracks
    cliques, all_tracks = utils.read_shs_file(shsf)
    track_ids = utils.load_pickle("SHS/track_ids_test.pk")
    clique_ids = utils.load_pickle("SHS/clique_ids_test.pk")

    # read codes file
    codesdir = args.codesdir[0]
    if codesdir is not None:
        if os.path.isfile(codesdir):
            c = utils.load_pickle(codesdir)
            feats = c[0]
            track_ids = c[1]
            clique_ids = c[2]
        else:
            feats, track_ids, clique_ids = load_codes(codesdir, 
                                                lda_idx=int(args.codesdir[1]))
        logger.info("Codes files read")
        print feats.shape
    else:
        # Read PCA file
        if args.pca[0] is not None:
            pca = utils.load_pickle(args.pca[0])[int(args.pca[1])]

        # read LDA file
        lda_file = args.lda
        if lda_file is not None:
            lda = utils.load_pickle(lda_file)

        utils.assert_file(args.dictfile)

        # Prepare Multiprocessing computation
        input = []
        pool = Pool(processes=args.N)
        for n in xrange(args.N):
            arg = {}
            arg["track_ids"] = track_ids
            arg["maindir"] = maindir
            arg["d"] = args.dictfile
            arg["N"] = n
            arg["clique_ids"] = clique_ids
            arg["outdir"] = args.outdir
            arg["origcodesdir"] = args.origcodesdir
            arg["pca_n"] = int(args.pca[1])
            arg["norm"] = args.norm
            input.append(arg)

        # Start computing the codes
        pool.map(compute_codes, input)

        # Done!
        logger.info("Codes computation done!")
        logger.info("Took %.2f seconds" % (time.time() - start_time))
        sys.exit()

    # Scores
    feats, clique_ids, track_ids = utils.clean_feats(feats, clique_ids, track_ids)
    stats = score(feats, clique_ids, N=len(all_tracks))

    # TODO: change file name
    utils.save_pickle(stats, "stats.pk")

    # done
    logger.info('Average rank per track: %.2f, clique: %.2f, MAP: %.2f%%' \
                % (anst.average_rank_per_track(stats),
                    anst.average_rank_per_clique(stats),
                    anst.mean_average_precision(stats) * 100))
    logger.info("Done! Took %.2f seconds" % (time.time() - start_time))

if __name__ == '__main__':
    main()
