import sys
import os
import re
import shutil
import collections
import datetime
import json

from textwrap import fill
import click

from nextlinux.cli.common import nextlinux_print, nextlinux_print_err
from nextlinux import navigator, controller, nextlinux_utils, nextlinux_auth, nextlinux_feeds, nextlinux_policy
from nextlinux.util import contexts, scripting

config = {}
imagelist = []


@click.group(short_help='Useful tools and operations on images and containers')
@click.option('--imageid',
              help='Process specified image ID',
              metavar='<imageid>')
@click.option('--image',
              help='Process specified image tag/ID/digest',
              metavar='<tag|imageid|digest>')
@click.pass_context
@click.pass_obj
def toolbox(nextlinux_config, ctx, image, imageid):
    """
    A collection of tools for operating on images and containers and building nextlinux modules.

    Subcommands operate on the specified image passed in as --image <imgid>

    """

    global config, imagelist, nav

    config = nextlinux_config
    ecode = 0

    try:

        # set up imagelist of imageIds
        if image:
            imagelist = [image]
            try:
                result = nextlinux_utils.discover_imageIds(imagelist)
            except ValueError as err:
                raise err
            else:
                imagelist = result
        elif imageid:
            if len(imageid) != 64 or re.findall("[^0-9a-fA-F]+", imageid):
                raise Exception(
                    "input is not a valid imageId (64 characters, a-f, A-F, 0-9)"
                )

            imagelist = [imageid]
        else:
            imagelist = []

        if ctx.invoked_subcommand not in [
                'import', 'delete', 'kubesync', 'images', 'show'
        ]:
            if not imagelist:
                raise Exception(
                    "for this operation, you must specify an image with '--image' or '--imageid'"
                )
            else:
                try:
                    nav = navigator.Navigator(
                        nextlinux_config=config,
                        imagelist=imagelist,
                        allimages=contexts['nextlinux_allimages'])
                except Exception as err:
                    nav = None
                    raise err

    except Exception as err:
        nextlinux_print_err('operation failed')
        ecode = 1

    if ecode:
        sys.exit(ecode)


@toolbox.command(name='delete',
                 short_help="Delete input image(s) from the Nextlinux DB")
@click.option(
    '--dontask',
    help=
    'Will delete the image from Nextlinux DB without asking for coinfirmation',
    is_flag=True)
def delete(dontask):
    ecode = 0

    try:
        for i in imagelist:
            imageId = None
            if contexts['nextlinux_db'].is_image_present(i):
                imageId = i
            else:
                try:
                    ret = nextlinux_utils.discover_imageId(i)
                    #imageId = ret.keys()[0]
                    imageId = ret
                except:
                    imageId = None

            if imageId:
                dodelete = False
                if dontask:
                    dodelete = True
                else:
                    try:
                        answer = raw_input("Really delete image '" + str(i) +
                                           "'? (y/N)")
                    except:
                        answer = "n"
                    if 'y' == answer.lower():
                        dodelete = True
                    else:
                        nextlinux_print("Skipping delete.")
                if dodelete:
                    try:
                        nextlinux_print("Deleting image '" + str(i) + "'")
                        contexts['nextlinux_db'].delete_image(imageId)
                    except Exception as err:
                        raise err
    except Exception as err:
        nextlinux_print_err('operation failed')
        ecode = 1
    sys.exit(ecode)


@toolbox.command(name='unpack',
                 short_help="Unpack the specified image into a temp location")
@click.option('--destdir',
              help='Destination directory for unpacked container image',
              metavar='<path>')
def unpack(destdir):
    """Unpack and Squash image to local filesystem"""

    if not nav:
        sys.exit(1)

    ecode = 0
    try:
        nextlinux_print("Unpacking images: " + ' '.join(nav.get_images()))
        result = nav.unpack(destdir=destdir)
        if not result:
            nextlinux_print_err("no images unpacked")
            ecode = 1
        else:
            for imageId in result:
                nextlinux_print("Unpacked image: " + imageId)
                nextlinux_print("Unpack directory: " + result[imageId])
    except:
        nextlinux_print_err("operation failed")
        ecode = 1

    contexts['nextlinux_allimages'].clear()

    sys.exit(ecode)


@toolbox.command(name='setup-module-dev',
                 short_help='Setup a module development environment')
@click.option('--destdir',
              help='Destination directory for module development environment',
              metavar='<path>')
def setup_module_dev(destdir):
    """
    Sets up a development environment suitable for working on nextlinux modules (queries, etc) in the specified directory.
    Creates a copied environment in the destination containing the module scripts, unpacked image(s) and helper scripts
    such that a module script that works in the environment can be copied into the correct installation environment and
    run with nextlinux explore <modulename> invocation and should work.

    """

    if not nav:
        sys.exit(1)

    ecode = 0
    try:
        nextlinux_print("Nextlinux Module Development Environment\n")
        helpstr = "This tool has set up an environment that represents what nextlinux will normally set up before running an analyzer, gate and/or query module.  Each section below includes some information along with a string that you can use to help develop your own nextlinux modules.\n"
        nextlinux_print(fill(helpstr, 80))
        nextlinux_print("")

        nextlinux_print("Setting up environment...")
        nextlinux_print("")

        result = nav.unpack(destdir=destdir)
        if not result:
            raise Exception("unable to unpack input image")

        for imageId in result:
            unpackdir = result[imageId]

            # copy nextlinux imageDB dir into unpacked environment
            imgdir = '/'.join([config.data['image_data_store'], imageId])
            tmpdatastore = '/'.join([unpackdir, 'data'])
            dstimgdir = '/'.join([tmpdatastore, imageId])

            if not os.path.exists(imgdir):
                nextlinux_print_err(
                    "Image must exist and have been analyzed before being used for module development."
                )
                break
            if not os.path.exists(tmpdatastore):
                os.makedirs(tmpdatastore)
            shutil.copytree(imgdir, dstimgdir, symlinks=True)

            # copy examples into the unpacked environment
            examples = {}
            basedir = '/'.join([unpackdir, "nextlinux-modules"])
            if not os.path.exists(basedir):
                os.makedirs(basedir)

                # copy the shell-utils
                os.makedirs('/'.join([basedir, 'shell-utils']))
                for s in os.listdir('/'.join(
                    [config.data['scripts_dir'], 'shell-utils'])):
                    shutil.copy(
                        '/'.join(
                            [config.data['scripts_dir'], 'shell-utils', s]),
                        '/'.join([basedir, 'shell-utils', s]))

            # copy any examples that exist in the nextlinux egg into the unpack dir
            for d in os.listdir(config.data['scripts_dir']):
                scriptdir = '/'.join([basedir, d])

                if os.path.exists(config.data['scripts_dir'] + "/examples/" +
                                  d):
                    if not os.path.exists(scriptdir):
                        os.makedirs(scriptdir)
                    for s in os.listdir(config.data['scripts_dir'] +
                                        "/examples/" + d):
                        thefile = '/'.join(
                            [config.data['scripts_dir'], "examples", d, s])
                        thefiledst = '/'.join([scriptdir, s])
                        if re.match(".*(\.sh)$", thefile):
                            examples[d] = thefiledst
                            shutil.copy(thefile, thefiledst)

            # all set, show how to use them
            nextlinux_print("\tImage: " + imageId[0:12])
            nextlinux_print("\tUnpack Directory: " + result[imageId])
            nextlinux_print("")
            analyzer_string = ' '.join([
                examples['analyzers'], imageId, tmpdatastore, dstimgdir,
                result[imageId]
            ])
            nextlinux_print("\tAnalyzer Command:\n\n\t" + analyzer_string)
            nextlinux_print("")

            nextlinux_utils.write_plainfile_fromstr(
                result[imageId] + "/queryimages", imageId + "\n")

            queryoutput = '/'.join([result[imageId], "querytmp/"])
            if not os.path.exists(queryoutput):
                os.makedirs(queryoutput)

            query_string = ' '.join([
                examples['queries'], result[imageId] + "/queryimages",
                tmpdatastore, queryoutput, "passwd"
            ])
            nextlinux_print("Query Command:\n\n\t" + query_string)
            nextlinux_print("")

            nextlinux_print("Next Steps: ")
            nextlinux_print(
                "\tFirst: run the above analyzer command and note the RESULT output"
            )
            nextlinux_print(
                "\tSecond: run the above query command and note the RESULT output, checking that the query was able to use the analyzer data to perform its search"
            )
            nextlinux_print(
                "\tThird: modify the analyzer/query modules as you wish, including renaming them and continue running/inspecting output until you are satisfied"
            )
            nextlinux_print(
                "\tFinally: when you're happy with the analyzer/query, copy them to next to existing nextlinux analyzer/query modules and nextlinux will start calling them as part of container analysis/query:\n"
            )
            nextlinux_print("\tcp " + examples['analyzers'] + " " +
                          config.data['scripts_dir'] +
                          "/analyzers/99_analyzer-example.sh")
            nextlinux_print("\tcp " + examples['queries'] + " " +
                          config.data['scripts_dir'] + "/queries/")
            nextlinux_print("\tnextlinux analyze --force --image " + imageId +
                          " --imagetype none")
            nextlinux_print("\tnextlinux query --image " + imageId +
                          " query-example")
            nextlinux_print("\tnextlinux query --image " + imageId +
                          " query-example passwd")
            nextlinux_print("\tnextlinux query --image " + imageId +
                          " query-example pdoesntexist")

    except:
        nextlinux_print_err("operation failed")
        ecode = 1

    contexts['nextlinux_allimages'].clear()

    sys.exit(ecode)


@toolbox.command(name='show-dockerfile')
def show_dockerfile():
    """Generate (or display actual) image Dockerfile"""

    if not nav:
        sys.exit(1)

    ecode = 0
    try:
        result = nav.run_query(['show-dockerfile', 'all'])
        if result:
            nextlinux_utils.print_result(config, result)

    except:
        nextlinux_print_err("operation failed")
        ecode = 1

    contexts['nextlinux_allimages'].clear()
    sys.exit(ecode)


@toolbox.command(name='show-layers')
def show_layers():
    """Show image layer IDs"""

    if not nav:
        sys.exit(1)

    ecode = 0
    try:
        result = nav.run_query(['show-layers', 'all'])
        if result:
            nextlinux_utils.print_result(config, result)

    except:
        nextlinux_print_err("operation failed")
        ecode = 1

    contexts['nextlinux_allimages'].clear()
    sys.exit(ecode)


@toolbox.command(name='show-familytree')
def show_familytree():
    """Show image family tree image IDs"""
    if not nav:
        sys.exit(1)

    ecode = 0
    try:
        result = nav.run_query(['show-familytree', 'all'])
        if result:
            nextlinux_utils.print_result(config, result)

    except:
        nextlinux_print_err("operation failed")
        ecode = 1

    contexts['nextlinux_allimages'].clear()
    sys.exit(ecode)


@toolbox.command(name='show-taghistory')
def show_taghistory():
    """Show history of all known repo/tags for image"""

    if not nav:
        sys.exit(1)

    ecode = 0
    try:
        result = nav.get_taghistory()
        if result:
            nextlinux_utils.print_result(config, result)

    except:
        nextlinux_print_err("operation failed")
        ecode = 1

    contexts['nextlinux_allimages'].clear()
    sys.exit(ecode)


@toolbox.command(name='show-analyzer-status')
def show_analyzer_status():
    """Show analyzer status for specified image"""

    ecode = 0
    try:
        image = contexts['nextlinux_allimages'][imagelist[0]]
        analyzer_status = contexts['nextlinux_db'].load_analyzer_manifest(
            image.meta['imageId'])
        result = {
            image.meta['imageId']: {
                'result': {
                    'header': [
                        'Analyzer', 'Status', '*Type', 'LastExec', 'Exitcode',
                        'Checksum'
                    ],
                    'rows': []
                }
            }
        }
        for script in analyzer_status.keys():
            adata = analyzer_status[script]
            nicetime = datetime.datetime.fromtimestamp(
                adata['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            try:
                row = [
                    script.split('/')[-1], adata['status'], adata['atype'],
                    nicetime,
                    str(adata['returncode']), adata['csum']
                ]
                result[image.meta['imageId']]['result']['rows'].append(row)
            except:
                pass
        if result:
            nextlinux_utils.print_result(config, result)
    except:
        nextlinux_print_err("operation failed")
        ecode = 1

    contexts['nextlinux_allimages'].clear()
    sys.exit(ecode)


@toolbox.command(name='export')
@click.option('--outfile',
              help='output file for exported image',
              required=True,
              metavar='<file.json>')
def export(outfile):
    """Export image nextlinux data to a JSON file."""

    if not nav:
        sys.exit(1)

    ecode = 0
    savelist = list()
    for imageId in imagelist:

        try:
            record = {}
            record['image'] = {}
            record['image']['imageId'] = imageId
            record['image']['imagedata'] = contexts[
                'nextlinux_db'].load_image_new(imageId)

            savelist.append(record)
        except Exception as err:
            nextlinux_print_err("could not find record for image (" +
                              str(imageId) + ")")
            ecode = 1

    if ecode == 0:
        try:
            if outfile == '-':
                print json.dumps(savelist, indent=4)
            else:
                with open(outfile, 'w') as OFH:
                    OFH.write(json.dumps(savelist))
        except Exception as err:
            nextlinux_print_err("operation failed: " + str(err))
            ecode = 1

    sys.exit(ecode)


@toolbox.command(name='kubesync')
def kubesync():
    """Communicate with kubernetes deployment via kubectl and save image names/IDs to local files"""

    ecode = 0

    try:
        images = nextlinux_utils.get_images_from_kubectl()
        if images:
            nextlinux_print("Writing image IDs to ./nextlinux_imageIds.kube")
            with open("nextlinux_imageIds.kube", 'w') as OFH:
                for imageId in images:
                    OFH.write(imageId + "\n")
            nextlinux_print("Writing image names to ./nextlinux_imageNames.kube")
            with open("nextlinux_imageNames.kube", 'w') as OFH:
                for imageId in images:
                    OFH.write(images[imageId] + "\n")

    except Exception as err:
        nextlinux_print_err("operation failed: " + str(err))
        ecode = 1

    sys.exit(ecode)


@toolbox.command(name='import')
@click.option(
    '--infile',
    help='input file that contains nextlinux image data from a previous export',
    type=click.Path(exists=True),
    metavar='<file.json>',
    required=True)
@click.option('--force',
              help='force import even if an image record is already in place',
              is_flag=True)
def image_import(infile, force):
    """Import image nextlinux data from a JSON file."""
    ecode = 0

    try:
        with open(infile, 'r') as FH:
            savelist = json.loads(FH.read())
    except Exception as err:
        nextlinux_print_err("could not load input file: " + str(err))
        ecode = 1

    if ecode == 0:
        for record in savelist:
            try:
                imageId = record['image']['imageId']
                if contexts['nextlinux_db'].is_image_present(
                        imageId) and not force:
                    nextlinux_print("image (" + str(imageId) +
                                  ") already exists in DB, skipping import.")
                else:
                    imagedata = record['image']['imagedata']
                    try:
                        rc = contexts['nextlinux_db'].save_image_new(
                            imageId, report=imagedata)
                        if not rc:
                            contexts['nextlinux_db'].delete_image(imageId)
                            raise Exception("save to nextlinux DB failed")
                    except Exception as err:
                        contexts['nextlinux_db'].delete_image(imageId)
                        raise err
            except Exception as err:
                nextlinux_print_err("could not store image (" + str(imageId) +
                                  ") from import file: " + str(err))
                ecode = 1

    sys.exit(ecode)


@toolbox.command(name='images')
@click.option('--no-trunc', help='Do not truncate imageIds', is_flag=True)
def images(no_trunc):
    ecode = 0

    import datetime

    try:
        nextlinuxDB = contexts['nextlinux_db']

        header = [
            "Repository", "Tag", "Image ID", "Distro", "Last Analyzed", "Size"
        ]
        result = {"multi": {'result': {'header': header, 'rows': []}}}

        hasData = False
        for image in nextlinuxDB.load_all_images_iter():
            try:
                imageId = image[0]
                imagedata = image[1]
                meta = imagedata['meta']

                name = meta['humanname']
                shortId = meta['shortId']
                size = meta['sizebytes']

                if no_trunc:
                    printId = imageId
                else:
                    printId = shortId

                patt = re.match("(.*):(.*)", name)
                if patt:
                    repo = patt.group(1)
                    tag = patt.group(2)
                else:
                    repo = "<none>"
                    tag = "<none>"

                oldtags = ','.join(imagedata['nextlinux_all_tags'])

                if meta['usertype']:
                    atype = meta['usertype']
                else:
                    atype = "<none>"

                distrometa = nextlinux_utils.get_distro_from_imageId(imageId)
                distro = distrometa['DISTRO'] + "/" + distrometa['DISTROVERS']

                amanifest = nextlinuxDB.load_analyzer_manifest(imageId)
                latest = 0
                if amanifest:
                    for a in amanifest.keys():
                        ts = amanifest[a]['timestamp']
                        if ts > latest:
                            latest = ts

                if latest:
                    timestr = datetime.datetime.fromtimestamp(
                        int(latest)).strftime('%m-%d-%Y %H:%M:%S')
                else:
                    timestr = "Not Analyzed"

                row = [
                    repo, tag, printId, distro, timestr,
                    str(round(float(size) / 1024.0 / 1024.0, 2)) + "M"
                ]
                result['multi']['result']['rows'].append(row)
                #t.add_row(row)
                hasData = True
            except Exception as err:
                raise err

        nextlinux_utils.print_result(config, result)

    except:
        nextlinux_print_err("operation failed")
        ecode = 1

    sys.exit(ecode)


@toolbox.command(name='show')
def show():
    """Show image summary information"""

    ecode = 0
    try:
        o = collections.OrderedDict()
        inimage = imagelist[0]
        nextlinuxDB = contexts['nextlinux_db']
        image = nextlinuxDB.load_image(inimage)
        if image:
            mymeta = image['meta']
            alltags_current = image['nextlinux_current_tags']
            distrodict = nextlinux_utils.get_distro_from_imageId(inimage)
            distro = distrodict['DISTRO']
            distrovers = distrodict['DISTROVERS']
            base = image['familytree'][0]

            o['IMAGEID'] = mymeta.pop('imageId', "N/A")
            o['REPOTAGS'] = alltags_current
            o['DISTRO'] = distro
            o['DISTROVERS'] = distrovers
            o['HUMANNAME'] = mymeta.pop('humanname', "N/A")
            o['SHORTID'] = mymeta.pop('shortId', "N/A")
            o['PARENTID'] = mymeta.pop('parentId', "N/A")
            o['BASEID'] = base
            o['IMAGETYPE'] = mymeta.pop('usertype', "N/A")

            for k in o.keys():
                if type(o[k]) is list:
                    s = ' '.join(o[k])
                else:
                    s = str(o[k])
                print k + "='" + s + "'"
        else:
            raise Exception("cannot locate input image in nextlinux DB")

    except Exception as err:
        nextlinux_print_err("operation failed")
        ecode = 1

    contexts['nextlinux_allimages'].clear()

    sys.exit(ecode)


def show_orig():
    """Show image summary information"""

    if not nav:
        sys.exit(1)

    ecode = 0
    try:
        image = contexts['nextlinux_allimages'][imagelist[0]]

        o = collections.OrderedDict()
        mymeta = {}
        mymeta.update(image.meta)
        o['IMAGEID'] = mymeta.pop('imageId', "N/A")
        o['REPOTAGS'] = image.get_alltags_current()
        o['DISTRO'] = image.get_distro()
        o['DISTROVERS'] = image.get_distro_vers()
        o['HUMANNAME'] = mymeta.pop('humanname', "N/A")
        o['SHORTID'] = mymeta.pop('shortId', "N/A")
        o['PARENTID'] = mymeta.pop('parentId', "N/A")
        o['BASEID'] = image.get_earliest_base()
        o['IMAGETYPE'] = mymeta.pop('usertype', "N/A")

        for k in o.keys():
            if type(o[k]) is list:
                s = ' '.join(o[k])
            else:
                s = str(o[k])
            print k + "='" + s + "'"

    except:
        nextlinux_print_err("operation failed")
        ecode = 1

    contexts['nextlinux_allimages'].clear()

    sys.exit(ecode)
