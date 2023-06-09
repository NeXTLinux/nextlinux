#!/usr/bin/env python

import sys
import os
import shutil
import re
import json
import time
import rpm
import subprocess

import nextlinux.nextlinux_utils

analyzer_name = "package_list"

try:
    config = nextlinux.nextlinux_utils.init_analyzer_cmdline(
        sys.argv, analyzer_name)
except Exception as err:
    print str(err)
    sys.exit(1)

imgname = config['imgid']
imgid = imgname
outputdir = config['dirs']['outputdir']
unpackdir = config['dirs']['unpackdir']

#if not os.path.exists(outputdir):
#    os.makedirs(outputdir)

pkglist = {}

try:
    allfiles = {}
    if os.path.exists(unpackdir + "/nextlinux_allfiles.json"):
        with open(unpackdir + "/nextlinux_allfiles.json", 'r') as FH:
            allfiles = json.loads(FH.read())
    else:
        fmap, allfiles = nextlinux.nextlinux_utils.get_files_from_path(unpackdir +
                                                                   "/rootfs")
        with open(unpackdir + "/nextlinux_allfiles.json", 'w') as OFH:
            OFH.write(json.dumps(allfiles))

    for tfile in allfiles.keys():
        patt = re.match(".*specifications.*\.gemspec$", tfile)
        if patt:
            thefile = '/'.join([unpackdir, 'rootfs', tfile])
            try:
                with open(thefile, 'r') as FH:
                    pdata = FH.read().decode('utf8')
                    precord = nextlinux.nextlinux_utils.gem_parse_meta(pdata)
                    for k in precord.keys():
                        record = precord[k]
                        pkglist[tfile] = json.dumps(record)
            except Exception as err:
                print "WARN: found gemspec but cannot parse (" + str(
                    tfile) + ") - exception: " + str(err)

except Exception as err:
    import traceback
    traceback.print_exc()
    raise err

if pkglist:
    ofile = os.path.join(outputdir, 'pkgs.gems')
    nextlinux.nextlinux_utils.write_kvfile_fromdict(ofile, pkglist)

sys.exit(0)
