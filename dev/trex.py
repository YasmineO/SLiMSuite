#!/usr/bin/python

# See below for name and description
# Copyright (C) 2016 Richard J. Edwards <redwards@cabbagesofdoom.co.uk>
#  
# This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2 of the License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with this program; if not, write to 
# the Free Software Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
# Author contact: <seqsuite@gmail.com> / School of Biotechnology and Biomolecular Sciences, UNSW, Sydney, Australia.
#
# To incorporate this module into your own programs, please see GNU Lesser General Public License disclaimer in rje.py

"""
Module:       TRex
Description:  Ty Repeat Extractor
Version:      0.2.0
Last Edit:    28/03/18
Copyright (C) 2016  Richard J. Edwards - See source code for GNU License Notice

Trim Function:
    TRex sniffs out the carcasses of fragmented Ty elements (or other repeats) littering the end of preassembly reads and
    removes them in the hope of improving the subsequent assembly. It is assumed that there is sufficient depth of
    coverage for full-length elements to be captured by longer reads, for which assembly of the ends will not be
    ambiguous. SMRTSCAPE "ftxcov" mode can be used to estimate this probability from the trimmed preassembly data.

    First, GABLAM is used for identifying elements that fall near the end of sequences. This is restricted to hits above
    length `minlength=X` [default=250]. In theory, this can be made as long as the required overlap for assembly. There
    might be a trade-off where unnecessary trimming of repeat fragments breaks up assembly of structural variants, whilst
    insufficient trimming leads to mid-repeat assembly graph nodes. Defaults err on the side of over-trimming: it is
    hoped that phasing tools using original subreads will overcome any reduction in differentiation of the sequences
    flanking structural variants.

    Identified repeats that fall within `endbuffer=X` [default 100 bp] of the end of a read will be removed and the
    truncated read saved (along with unaffected reads) in a `*.trex.fasta` file. In addition to the region matching the
    repeat, the end of the read and an additional flanking regions specified by `trimflank=X` [default 200 bp] will be
    removed. If `trimflank<0`, the hit region itself will be truncated prior to read trimming, i.e. a portion of the
    repeat will be left on. For example, `trimflank=-250` will leave 250 bp of the repeat on the end of the sequence,
    which will generate ends similar to those ignored under the default `minlength=250`. Only hits within `endbuffer=X`
    of the end will be trimmed. This may need to be changed if there is the danger of a longer stretch in the middle of a
    repeat sequence failing to have enough homology between the `seqin` repeat sequences and the occurrences in the read.
    TRex will be tested and optimised for yeast Ty elements.

    To avoid long tandem repeats disappearing completely from the assembly, trimmed reads are re-scanned for additional
    terminal repeats after a single repeat is snipped off either or both ends. By default (`trmode=keep`), reads that
    have a terminal repeat element post-trimming are retained in the preassembly at full length. Alternatively, TRex can
    keep trimming back terminal repeats until there are none by setting `trmode=iterate`. Third third alternative is
    `trmode=trim`, which will only trim the end fragment and leave internal repeats untrimmed; it is not clear under what
    circumstances this would directly be useful but running TRex several times with `trmode=trim` will iteratively remove
    tandem repeats of elements with higher resolution tracking of the reads affected. (The end product should be
    identical to running with `trmode=iterate`.)

    In addition to the main `*.trex.fasta` output, a `*.trex.tdt` table will be generated of the sequences trimmed from
    the original preassembly reads:
    - Read = Preassembly read being trimmed.
    - Length = The untrimmed length of the read.
    - Start = The start of the trimmed read relative to the original read (1-L).
    - End = The end of the trimmed read relative to the original read (1-L).
    - BegRpt = Repeat element used for trimming 5' end. (The one with the longest terminal hit will be used.)
    - EndRpt = Repeat element used for trimming 3' end. (The one with the longest terminal hit will be used.)

    By default, there will also be `*.blast` and `*.local.tdt` files generated by GABLAM as part of the search. Keeping
    these will enable more rapid re-running of TRex with different trim settings. NOTE: to re-run with more relaxed
    minlength/minid settings, the `*.local.tdt` should first be removed.

Hunt Function:


Commandline:
    ### ~ Input/Output options ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
    seqin=FASFILE       : Fasta file of representative repeat sequences for removal []
    basefile=FILE       : Root of output file names [preassembly or searchdb basefile]
    keepblast=T/F       : Whether to keep the BLAST output of the repeats versus reads [True]
    keeplocal=T/F       : Whether to keep the GABLAM local BLAST hit table of repeated versus reads [True]
    cleandb=T/F         : Whether to clean up (delete) files generated during `makedb` formatting [False]

    ### ~ Repeat Element Identification options ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
    trex=X              : TRex run mode: trim/hunt/strip/mask/extract/repoint [hunt]
    minlength=INT       : Minimum length of a fragment (local BLAST hit) worthy of consideration [250]
    minid=PERC          : Minimum %identity of a fragment (local BLAST hit) worthy of consideration [60.0]

    ### ~ Read Trimming options ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
    preassembly=FASFILE : Fasta file of preassembly reads []
    endbuffer=X         : Max distance from end of sequence to flag repeat for trimming [100]
    trimflank=X         : Additional flanking nucleotides to trim off the end of the sequence [200]
    trmode=X            : How to handle terminal tandem repeats (keep/trim/iterate) [keep]

    ### ~ Repeat Hunting/Stripping/Masking options ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
    searchdb=FASFILE    : Genome or assembly in which to find and classify TEs []
    refgenome=FASFILE   : Reference Genome to use for establishing flanking positions []


    ### ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
"""
#########################################################################################################################
### SECTION I: GENERAL SETUP & PROGRAM DETAILS                                                                          #
#########################################################################################################################
import os, string, sys, time
slimsuitepath = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)),'../')) + os.path.sep
sys.path.append(os.path.join(slimsuitepath,'libraries/'))
sys.path.append(os.path.join(slimsuitepath,'tools/'))
### User modules - remember to add *.__doc__ to cmdHelp() below ###
import rje, rje_db, rje_obj, rje_seqlist, rje_sequence
import gablam
#########################################################################################################################
def history():  ### Program History - only a method for PythonWin collapsing! ###
    '''
    # 0.0.0 - Initial Compilation.
    # 0.1.0 - Added trmode=X : How to handle tandem repeats (keep/trim/iterate) [keep]
    # 0.1.1 - Fixed IOEror typo.
    # 0.2.0 - Added TR Hunt mode based on processing of GABLAM unique searches.
    '''
#########################################################################################################################
def todo():     ### Major Functionality to Add - only a method for PythonWin collapsing! ###
    '''
    # [Y] : Populate Module Docstring with basic info.
    # [Y] : Populate makeInfo() method with basic info.
    # [Y] : Add full description of program to module docstring.
    # [Y] : Create initial working version of program.
    # [N] : Add REST outputs to restSetup() and restOutputOrder()
    # [ ] : Add to SLiMSuite or SeqSuite.
    # [?] : maxlength=PERC      : Maximum length of a repeat hit as % of repeat unit. Zero will purge all terminal repeats [0.95]
    # [X] : Enable endbuffer to accept values < 1 as proportion of repeat sequences.
    # [Y] : trmode=X : How to handle tandem repeats (keep/trim/iterate) [keep]
    # [ ] : Add minreadlen=X : minimum read length to include in preassembly.
    # [ ] : Add mintrexlen=X : minimum read length for a read with terminal repeat sequence.
    '''
#########################################################################################################################
def makeInfo(): ### Makes Info object which stores program details, mainly for initial print to screen.
    '''Makes Info object which stores program details, mainly for initial print to screen.'''
    (program, version, last_edit, copy_right) = ('TRex', '0.2.0', 'March 2018', '2017')
    description = 'Ty Repeat Extractor'
    author = 'Dr Richard J. Edwards.'
    comments = ['TRex trims fragmented Ty elements (or other repeats) from the end of',
                '  preassembly reads in the hope of improving the subsequent assembly.',
                'NOTE: This program is still in development and has not been published.',
                rje_obj.zen()]
    return rje.Info(program,version,last_edit,description,author,time.time(),copy_right,comments)
#########################################################################################################################
def cmdHelp(info=None,out=None,cmd_list=[]):   ### Prints *.__doc__ and asks for more sys.argv commands
    '''Prints *.__doc__ and asks for more sys.argv commands.'''
    try:### ~ [1] ~ Setup ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
        if not info: info = makeInfo()
        if not out: out = rje.Out()
        ### ~ [2] ~ Look for help commands and print options if found ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
        cmd_help = cmd_list.count('help') + cmd_list.count('-help') + cmd_list.count('-h')
        if cmd_help > 0:
            print '\n\nHelp for %s %s: %s\n' % (info.program, info.version, time.asctime(time.localtime(info.start_time)))
            out.verbose(-1,4,text=__doc__)
            if rje.yesNo('Show general commandline options?'): out.verbose(-1,4,text=rje.__doc__)
            if rje.yesNo('Quit?'): sys.exit()           # Option to quit after help
            cmd_list += rje.inputCmds(out,cmd_list)     # Add extra commands interactively.
        elif out.stat['Interactive'] > 1: cmd_list += rje.inputCmds(out,cmd_list)    # Ask for more commands
        ### ~ [3] ~ Return commands ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
        return cmd_list
    except SystemExit: sys.exit()
    except KeyboardInterrupt: sys.exit()
    except: print 'Major Problem with cmdHelp()'
#########################################################################################################################
def setupProgram(): ### Basic Setup of Program when called from commandline.
    '''
    Basic Setup of Program when called from commandline:
    - Reads sys.argv and augments if appropriate
    - Makes Info, Out and Log objects
    - Returns [info,out,log,cmd_list]
    '''
    try:### ~ [1] ~ Initial Command Setup & Info ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
        info = makeInfo()                                   # Sets up Info object with program details
        cmd_list = rje.getCmdList(sys.argv[1:],info=info)   # Reads arguments and load defaults from program.ini
        out = rje.Out(cmd_list=cmd_list)                    # Sets up Out object for controlling output to screen
        out.verbose(2,2,cmd_list,1)                         # Prints full commandlist if verbosity >= 2 
        out.printIntro(info)                                # Prints intro text using details from Info object
        cmd_list = cmdHelp(info,out,cmd_list)               # Shows commands (help) and/or adds commands from user
        log = rje.setLog(info,out,cmd_list)                 # Sets up Log object for controlling log file output
        return (info,out,log,cmd_list)                      # Returns objects for use in program
    except SystemExit: sys.exit()
    except KeyboardInterrupt: sys.exit()
    except: print 'Problem during initial setup.'; raise
#########################################################################################################################
### END OF SECTION I                                                                                                    #
#########################################################################################################################

                                                    ### ~ ### ~ ###

#########################################################################################################################
### SECTION II: TRex Class                                                                                              #
#########################################################################################################################
class TRex(rje_obj.RJE_Object):
    '''
    TRex Class. Author: Rich Edwards (2015).

    Str:str
    - SeqIn=FASFILE       : Fasta file of representative repeat sequences for removal []
    - Preassembly=FASFILE : Fasta file of preassembly reads []
    - RefGenome=FASFILE   : Reference Genome to use for establishing flanking positions []
    - SearchDB=FASFILE    : Genome or assembly in which to find and classify TEs []
    - TRex=X              : TRex run mode: trim/hunt [trim]
    - TRMode=X            : How to handle terminal tandem repeats (keep/trim/iterate) [keep]

    Bool:boolean
    - CleanDB=T/F         : Whether to clean up (deleted) files generated during preassembly `makedb` formatting [False]
    - KeepLocal=T/F       : Whether to keep the GABLAM local BLAST hit table of repeated versus reads [True]

    Int:integer
    - EndBuffer=X         : Max distance from end of sequence to flag repeat for trimming [100]
    - MinLength=INT       : Minimum length of a fragment (local BLAST hit) worthy of consideration [250]
    - TrimFlank=X         : Additional flanking nucleotides to trim off the end of the sequence [200]

    Num:float
    - MinID=PERC          : Minimum %identity of a fragment (local BLAST hit) worthy of consideration [60.0]

    File:file handles with matching str filenames
    
    List:list

    Dict:dictionary    

    Obj:RJE_Objects
    - DB = Database object, shared with GABLAM
    - GABLAM = Main GABLAM Object for seqin vs preassembly search
    '''
#########################################################################################################################
    ### <1> ### Class Initiation etc.: sets attributes                                                                  #
#########################################################################################################################
    def _setAttributes(self):   ### Sets Attributes of Object
        '''Sets Attributes of Object.'''
        ### ~ Basics ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
        self.strlist = ['Preassembly','RefGenome','SearchDB','SeqIn','TRex','TRMode']
        self.boollist = ['CleanDB','KeepLocal']
        self.intlist = ['EndBuffer','MinLength','TrimFlank']
        self.numlist = ['MinID']
        self.filelist = []
        self.listlist = []
        self.dictlist = []
        self.objlist = []
        ### ~ Defaults ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
        self._setDefaults(str='None',bool=False,int=0,num=0.0,obj=None,setlist=True,setdict=True,setfile=True)
        self.setStr({'TRex':'hunt','TRMode':'keep'})
        self.setBool({'CleanDB':False,'KeepLocal':True})
        self.setInt({'EndBuffer':100,'MinLength':250,'TrimFlank':200})
        self.setNum({'MinID':60.0})
        ### ~ Other Attributes ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
        self._setForkAttributes()   # Delete if no forking
#########################################################################################################################
    def _cmdList(self):     ### Sets Attributes from commandline
        '''
        Sets attributes according to commandline parameters:
        - see .__doc__ or run with 'help' option
        '''
        for cmd in self.cmd_list:
            try:
                self._generalCmd(cmd)   ### General Options ### 
                self._forkCmd(cmd)  # Delete if no forking
                ### Class Options (No need for arg if arg = att.lower()) ### 
                #self._cmdRead(cmd,type='str',att='Att',arg='Cmd')  # No need for arg if arg = att.lower()
                self._cmdReadList(cmd,'str',['TRex','TRMode'])   # Normal strings
                #self._cmdReadList(cmd,'path',['Att'])  # String representing directory path 
                self._cmdReadList(cmd,'file',['RefGenome','SearchDB','SeqIn','Preassembly'])  # String representing file path
                #self._cmdReadList(cmd,'date',['Att'])  # String representing date YYYY-MM-DD
                self._cmdReadList(cmd,'bool',['CleanDB','KeepLocal'])  # True/False Booleans
                self._cmdReadList(cmd,'int',['EndBuffer','MinLength','TrimFlank'])   # Integers
                #self._cmdReadList(cmd,'float',['Att']) # Floats
                self._cmdReadList(cmd,'perc',['MinID']) # Percentage (Converts to 0-100)
                #self._cmdReadList(cmd,'min',['Att'])   # Integer value part of min,max command
                #self._cmdReadList(cmd,'max',['Att'])   # Integer value part of min,max command
                #self._cmdReadList(cmd,'list',['Att'])  # List of strings (split on commas or file lines)
                #self._cmdReadList(cmd,'clist',['Att']) # Comma separated list as a *string* (self.str)
                #self._cmdReadList(cmd,'glist',['Att']) # List of files using wildcards and glob
                #self._cmdReadList(cmd,'cdict',['Att']) # Splits comma separated X:Y pairs into dictionary
                #self._cmdReadList(cmd,'cdictlist',['Att']) # As cdict but also enters keys into list
            except: self.errorLog('Problem with cmd:%s' % cmd)
#########################################################################################################################
    ### <2> ### Main Class Backbone                                                                                     #
#########################################################################################################################
    def run(self):  ### Main run method
        '''Main run method.'''
        try:### ~ [1] ~ Setup ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
            if not self.setup(): return False
            ### ~ [2] ~ Add main run code here ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
            if self.getStrLC('TRex') == 'trim': return self.tRex()
            elif self.getStrLC('TRex') == 'hunt': return self.huntTE()
            elif self.getStrLC('TRex') == 'strip': return self.stripTE()
            elif self.getStrLC('TRex') == 'mask': return self.maskTE()
            elif self.getStrLC('TRex') == 'extract': return self.extractTE()
            elif self.getStrLC('TRex') == 'repoint': return self.repointTE()
            else:
                self.printLog('#TREX','%s mode not recognised or not yet implemented!' % self.getStrLC('TRex'))
        except:
            self.errorLog(self.zen())
            raise   # Delete this if method error not terrible
#########################################################################################################################
    def setup(self):    ### Main class setup method.
        '''Main class setup method.'''
        try:### ~ [1] Setup ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
            ## ~ [1a] Setup basefile for analysis ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##
            if not rje.exists(self.getStr('SeqIn')): raise IOError('seqin=FILE must be set!')
            if self.getStrLC('TRex') == 'trim':
                if not rje.exists(self.getStr('Preassembly')): raise IOError('preassembly=FILE must be set!')
                if not self.baseFile(return_none=''): self.baseFile(rje.baseFile(self.getStr('Preassembly'),strip_path=True))
            elif self.getStrLC('TRex') in ['hunt','strip','mask','extract']:
                if not rje.exists(self.getStr('SearchDB')): raise IOError('searchdb=FILE must be set!')
                if not self.baseFile(return_none=''): self.baseFile(rje.baseFile(self.getStr('SearchDB'),strip_path=True))
            elif self.getStrLC('TRex') == 'repoint':
                #i# Makes all TEs point the same way. Does not need assembly or subreads
                if not self.baseFile(return_none=''): self.baseFile(rje.baseFile(self.getStr('SeqIn'),strip_path=True))
            else: raise ValueError('trex=%s not recognised' % self.getStrLC('TRex'))
            self.printLog('#BASE','Basename for main IO: %s' % self.baseFile())
            ## ~ [1a] Look for local results ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##
            if self.getStrLC('TRex') in ['trim','repoint']: lfile = '%s.local.tdt' % self.baseFile()
            else: lfile = '%s.unique.tdt' % self.baseFile()
            if rje.exists(lfile):   # Load existing file for reanalysis
                db = self.obj['DB'] = rje_db.Database(self.log,self.cmd_list+['tuplekeys=T'])
                db.baseFile(self.baseFile())
                if self.getStrLC('TRex') in ['trim','repoint']: db.addTable(lfile,mainkeys=['Qry','Hit','AlnNum'],name='Local')
                else:
                    udb = db.addTable(lfile,mainkeys=['Query','Hit','AlnID'],name='Local')
                    udb.renameField('Query','Qry')
                if self.getStrLC('TRex') in ['hunt']: db.addTable(name='gablam',mainkeys=['Qry','Hit'],expect=True)
            ## ~ [1b] Else, run GABLAM ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##
            else:
                gcmd = ['fullblast=T','keepblast=T']
                if self.getStrLC('TRex') in ['trim']: gcmd += ['fullres=F','hitsum=F']
                else: gcmd += ['fullres=T','hitsum=T']
                gcmd += ['blastp=blastn'] + self.cmd_list
                gcmd += ['local=%s' % self.getBool('KeepLocal'),'localmin=%d' % self.getInt('MinLength'),'localidmin=%f' % self.getNum('MinID')]
                gcmd += ['basefile=%s' % self.baseFile()]
                if self.getStrLC('TRex') in ['hunt','strip','mask']: gcmd += ['localunique=T']
                if self.getStrLC('TRex') in ['trim']: gcmd += ['searchdb=%s' % self.getStr('Preassembly')]
                if self.getStrLC('TRex') in ['repoint']: gcmd += ['searchdb=%s' % self.getStr('SeqIn'),'maxall=1']
                gab = self.obj['GABLAM'] = gablam.GABLAM(self.log,gcmd)
                gab.gablam()
                db = self.obj['DB'] = gab.obj['BLAST'].db()
                if self.getBool('CleanDB'): rje_blast.cleanupDB(self,gab.getStr('SearchDB'))
                if self.getStrLC('TRex') not in ['trim','repoint']:
                    db.deleteTable('Local')
                    udb = self.db('unique')
                    udb.rename('Local')
                    udb.renameField('Query','Qry')
            ## ~ [1c] Check tables loaded OK ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##
            for table in self.db().tables():
                self.debug('%s: %s' % (table.name(),table.entryNum()))
            return True     # Setup successful
        except: self.errorLog('Problem during %s setup.' % self.prog()); return False  # Setup failed
#########################################################################################################################
    ### <3> ### Additional Class Methods                                                                                #
#########################################################################################################################
    def tRex(self):  ### Removes repeats from the end of Ty elements.
        '''
        TRex sniffs out the carcasses of fragmented Ty elements (or other repeats) littering the end of preassembly reads and
        removes them for reassembly with Falcon.

        First, GABLAM is used for identifying elements that fall near the end of sequences. This is restricted to hits above
        length `minlength=X` [default=250]. In theory, this can be made as long as the required overlap for assembly. There
        might be a trade-off where unnecessary trimming of repeat fragments breaks up assembly of structural variants, whilst
        insufficient trimming leads to mid-repeat assembly graph nodes. Defaults err on the side of over-trimming: it is
        hoped that phasing tools using original subreads will overcome any reduction in differentiation of the sequences
        flanking structural variants.

        Identified repeats that fall within `endbuffer=X` [default 100 bp] of the end of a read will be removed and the
        truncated read saved (along with unaffected reads) in a `*.trex.fasta` file. In addition to the region matching the
        repeat, the end of the read and an additional flanking regions specified by `trimflank=X` [default 200 bp] will be
        removed. If `trimflank<0`, the hit region itself will be truncated prior to read trimming, i.e. a portion of the
        repeat will be left on. For example, `trimflank=-250` will leave 250 bp of the repeat on the end of the sequence,
        which will generate ends similar to those ignored under the default `minlength=250`. Only hits within `endbuffer=X`
        of the end will be trimmed. This may need to be changed if there is the danger of a longer stretch in the middle of a
        repeat sequence failing to have enough homology between the `seqin` repeat sequences and the occurrences in the read.
        TRex will be tested and optimised for yeast Ty elements.

        To avoid long tandem repeats disappearing completely from the assembly, only a single repeat is snipped off the end.
        TRex can always be run several times to remove more if required.

        In addition to the main `*.trex.fasta` output, a `*.trex.tdt` table will be generated of the sequences trimmed from
        the original preassembly reads:
        - Read = Preassembly read being trimmed.
        - Length = The untrimmed length of the read.
        - Start = The start of the trimmed read relative to the original read (1-L).
        - End = The end of the trimmed read relative to the original read (1-L).
        - BegRpt = Repeat element used for trimming 5' end. (The one with the longest terminal hit will be used.)
        - EndRpt = Repeat element used for trimming 3' end. (The one with the longest terminal hit will be used.)

        By default, there will also be `*.blast` and `*.local.tdt` files generated by GABLAM as part of the search. Keeping
        these will enable more rapid re-running of TRex with different trim settings. NOTE: to re-run with more relaxed
        minlength/minid settings, the `*.local.tdt` should first be removed.
        '''
        try:### ~ [1] Setup ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
            scmd = self.cmd_list + ['seqin=%s' % self.getStr('Preassembly'),'autoload=T''seqmode=file']
            preseq = rje_seqlist.SeqList(self.log,scmd)
            ldb = self.db('Local')
            ldb.dataFormat({'AlnNum':'int','BitScore':'num','Expect':'num','Identity':'int','QryStart':'int','QryEnd':'int','SbjStart':'int','SbjEnd':'int','Length':'int'})
            ldb.index('Hit')
            tdb = self.db().addEmptyTable('trex',['Read','Length','Start','End','BegRpt','EndRpt'],['Read'])
            # - Read = Preassembly read being trimmed.
            # - Length = The untrimmed length of the read.
            # - Start = The start of the trimmed read relative to the original read (1-L).
            # - End = The end of the trimmed read relative to the original read (1-L).
            # - BegRpt = Repeat element used for trimming 5' end. (The one with the longest terminal hit will be used.)
            # - EndRpt = Repeat element used for trimming 3' end. (The one with the longest terminal hit will be used.)
            tfas = '%s.trex.fasta' % self.baseFile()
            rje.backup(self,tfas)
            TFAS = open(tfas,'w')
            flankx = self.getInt('TrimFlank')
            trmode = self.getStrLC('TRMode')
            if trmode not in ['keep','trim','iterate']:
                self.warnLog('trmode=%s not recognised: set trmode=keep. (Allowed: keep/trim/iterate)' % trmode)
                trmode = 'keep'
            self.printLog('#MODE','TRMode: %s' % trmode)
            ### ~ [2] Filter local table ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
            sx = 0.0; stot = preseq.seqNum(); tx = 0
            for seq in preseq.seqs():
                self.progLog('\r#TREX','Processing preassembly reads: %.2f%%' % (sx*100.0/stot)); sx += 1
                seqlen = preseq.seqLen(seq)
                sname = preseq.shortName(seq)
                sequence = preseq.seqSequence(seq)
                sentry = {'Read':sname,'Length':seqlen,'Start':1,'End':seqlen,'BegRpt':'','EndRpt':'','TR':0}
                trex = 0; trexloop = True; trexcycle = 0; trextrim = True
                while trexloop:
                    begx = sentry['Start'] + self.getInt('EndBuffer') - 1   # Ty start hit must start upto position begx (1-L)
                    endx = sentry['End'] - self.getInt('EndBuffer')         # Ty end hit must end beyond endx (1-L)
                    trexloop = False; trexcycle += 1
                    for entry in ldb.indexEntries('Hit',sname):
                        beg = min(entry['SbjStart'],entry['SbjEnd'])
                        end = max(entry['SbjStart'],entry['SbjEnd'])
                        if beg <= begx:     #Hit are start of sequence
                            trex += 1
                            end = min(end+flankx,seqlen)
                            # Check for -ve flankx skipping Hit
                            if end < beg: continue
                            # Update if longer than current Rpt (if any)
                            if (end + 1) > sentry['Start']:
                                sentry['Start'] = end + 1
                                sentry['BegRpt'] = entry['Qry']
                                if trmode in ['keep','iterate']: trexloop = True
                                if trmode == 'keep' and trexcycle > 1: trextrim = False
                        elif end > endx:    #Hit at end of sequence
                            trex += 1
                            beg = max(1,beg-flankx)
                            # Check for -ve flankx skipping Hit
                            if beg > end: continue
                            # Update if longer than current Rpt (if any)
                            if (beg - 1) < sentry['End']:
                                sentry['End'] = beg - 1
                                sentry['EndRpt'] = entry['Qry']
                                if trmode in ['keep','iterate']: trexloop = True
                                if trmode == 'keep' and trexcycle > 1: trextrim = False
                if trex and trextrim:
                    tdb.addEntry(sentry)
                    if sentry['End'] < sentry['Start']:     # Entirely filtered!
                        self.printLog('#FILT','Read %s (%s bp) entirely filtered by repeat fragments!' % (sname,rje.iStr(seqlen)))
                    else:
                        sequence = sequence[sentry['Start']-1:sentry['End']]
                        TFAS.write('>%s %d terminal repeats (Pos %s:%s)\n%s\n' % (sname,trex,rje.iStr(sentry['Start']),rje.iStr(sentry['End']),sequence))
                        tx += 1
                        if self.v() > 0: self.printLog('#TRIM','>%s %d terminal repeats (Pos %s:%s)' % (sname,trex,rje.iStr(sentry['Start']),rje.iStr(sentry['End'])))
                elif trex:
                    TFAS.write('>%s %d terminal repeats; internal tandem repeat.\n%s\n' % (sname,trex,sequence))
                    if self.v() > 0: self.printLog('#KEEP','>%s %d terminal repeats; internal tandem repeat (trmode=keep).' % (sname,trex))
                    tx += 1
                else:
                    TFAS.write('>%s %d terminal repeats\n%s\n' % (sname,trex,sequence))
                    tx += 1
            self.printLog('\r#TREX','%s of %s preassembly reads output to %s' % (rje.iStr(tx),rje.iStr(sx),tfas))
            TFAS.close()
            tdb.saveToFile()

            return True
        except: self.errorLog('%s.tRex() error' % self.prog()); return False
#########################################################################################################################
    def repointTE(self):  ### Repoints TEs to face same direction, optionally removing redundancy
        '''Repoints TEs to face same direction, optionally removing redundancy.'''
        try:### ~ [1] Setup ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
            seqlist = rje_seqlist.SeqList(self.log,self.cmd_list+['autoload=T'])  #i# This will handle redundancy
            ldb = self.db('Local')
            ldb.dataFormat({'AlnNum':'int','BitScore':'num','Expect':'num','Identity':'int','QryStart':'int','QryEnd':'int','SbjStart':'int','SbjEnd':'int','Length':'int'})
            ldb.index('Qry')
            ldb.index('Hit')

            fwd = {}     # {Qry:+/-}
            queries = rje.sortKeys(ldb.index('Qry'))
            while queries:
                qry = queries.pop(0)
                if not fwd or qry not in fwd: fwd[qry] = True
                qfwd = fwd[qry]
                if qfwd: self.printLog('#FWD',qry)
                else: self.printLog('#REV',qry)
                qhits = []
                for entry in ldb.indexEntries('Qry',qry):
                    hit = entry['Hit']
                    if hit in qhits: continue
                    if hit not in ldb.index('Qry'): hit = string.split(hit,'__')[-1]
                    if hit not in ldb.index('Qry'): raise ValueError('Hit %s not found in Queries' % hit)
                    if qry == hit: continue
                    if entry['SbjStart'] < entry['SbjEnd']: hfwd = qfwd
                    else: hfwd = not qfwd
                    if hit in fwd and fwd[hit] != hfwd:
                        self.warnLog('Direction conflict for %s!' % hit)
                    else: fwd[hit] = hfwd
                    qhits.append(hit)
                for hit in qhits[0:]:
                    if hit in queries: queries.remove(hit)
                    else: qhits.remove(hit)
                queries = qhits + queries

            tfile = '%s.repoint.fas' % self.baseFile()
            SEQFILE = open(tfile,'w'); sx = 0
            for seq in seqlist.seqs():
                hit = seqlist.seqAcc(seq)
                if hit not in ldb.index('Qry'): hit = seqlist.shortName(seq)
                if hit not in ldb.index('Qry'): self.printLog('#FILT','%s filtered' % seqlist.shortName(seq)); continue
                (name, sequence) = seqlist.getSeq(seq,'tuple')
                if not fwd.pop(hit):
                    name += ' RevComp'
                    sequence = rje_sequence.reverseComplement(sequence)
                SEQFILE.write('>%s\n%s\n' % (name,sequence)); sx += 1
            self.printLog('#SAVE','%s sequences saved to %s' % (sx,tfile))
            SEQFILE.close()

            if fwd:
                for hit in rje.sortKeys(fwd):
                    self.warnLog('TE %s not processed' % hit)
                raise ValueError('%d TE not processed!' % len(fwd))

            return True     # Run successful
        except: self.errorLog('Problem during %s repointTE.' % self.prog()); return False  # Failed
#########################################################################################################################
    def maskTE(self):  ### Masks TEs from searchDB sequences and outputs as *.temask.fas
        '''Masks TEs from searchDB sequences and outputs as *.temask.fas.'''
        try:### ~ [1] Setup ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
            return self.stripTE(mask=True)
        except: self.errorLog('Problem during %s maskTE.' % self.prog()); return False  # Failed
#########################################################################################################################
    def extractTE(self):  ### Extracts TEs from hit sequences and outputs to a file.
        '''Extracts TEs from hit sequences and outputs to a file.'''
        try:### ~ [1] Setup ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
            #?# Would this not be better off just using GABLAM?
            self.printLog('#TREX','%s mode not yet implemented!' % self.getStrLC('TRex'))
            return True     # Run successful
        except: self.errorLog('Problem during %s extractTE.' % self.prog()); return False  # Failed
#########################################################################################################################
    def stripTE(self,mask=False):  ### Strips TE hits from searchDB and outputs as *.testrip.fas
        '''Strips TE hits from searchDB and outputs as *.testrip.fas.'''
        try:### ~ [1] Setup ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
            seqlist = rje_seqlist.SeqList(self.log,self.cmd_list+['autoload=T','seqin=%s' % self.getStr('SearchDB')])
            db = self.obj['DB']
            ldb = self.db('Local')
            ldb.dataFormat({'AlnNum':'int','BitScore':'num','Expect':'num','Identity':'int','QryStart':'int','QryEnd':'int','SbjStart':'int','SbjEnd':'int','Length':'int'})
            ldb.indexReport('Hit')
            ### ~ [2] Output ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
            tehits = {}
            for entry in ldb.entries():
                hit = entry['Hit']
                if hit not in tehits: tehits[hit] = []
                x = min((entry['SbjStart'],entry['SbjEnd']))
                y = max((entry['SbjStart'],entry['SbjEnd']))
                tehits[hit].append((x,y))
            for hit in tehits:
                tehits[hit].sort()
                if len(tehits[hit]) > 1:
                    for i in range(len(tehits[hit])-1):
                        if tehits[hit][i][1] >= tehits[hit][i+1][0]:
                            raise ValueError('Overlapping %s TE hits! Should not be possible!' % hit)
                tehits[hit].reverse()

            if mask: seqfile = '%s.temask.fas' % self.baseFile()
            else: seqfile = '%s.testrip.fas' % self.baseFile()
            rje.backup(self,seqfile)
            SEQFILE = open(seqfile,'w')
            for seq in seqlist.seqs():
                hit = seqlist.shortName(seq)
                (name, sequence) = seqlist.getSeq(seq,'tuple')
                prelen = len(sequence)
                if hit in tehits:
                    for (x,y) in tehits[hit]:
                        if mask:
                            sequence = sequence[:x-1] + 'N' * (y-x+1) + sequence[y-1:]
                            mx += y-x+1
                        else: sequence = sequence[:x-1] + sequence[y-1:]
                    if mask:
                        if prelen != len(sequence): raise ValueError('Mask fuckup')
                        self.printLog('#MASK','Masked %d TEs from %s: %s of %s nt -> N' % (len(tehits[hit]),hit,rje.iStr(mx),rje.iLen(sequence)))
                        name += '%d TEs masked' % len(tehits[hit])
                    else:
                        self.printLog('#STRIP','Stripped %d TEs from %s: %s nt -> %s nt' % (len(tehits[hit]),hit,rje.iStr(prelen),rje.iLen(sequence)))
                        name += '%d TEs stripped' % len(tehits[hit])
                    tehits.pop(hit)
                else:
                    if mask: self.printLog('#MASK','No TEs in %s to mask' % hit)
                    else: self.printLog('#STRIP','No TEs in %s to strip' % hit)
                SEQFILE.write('>%s\n%s\n' % (name,sequence))
            self.printLog('#SAVE','%s sequences saved to %s' % (seqlist.seqNum(),seqfile))
            SEQFILE.close()

            if tehits:
                for hit in rje.sortKeys(tehits):
                    self.warnLog('TE hits for %s not processed' % hit)
                raise ValueError('TE hits for %d hits not processed!' % len(tehits))

            return True     # Run successful
        except: self.errorLog('Problem during %s stripTE.' % self.prog()); return False  # Failed
#########################################################################################################################
    def huntTE(self):  ### Repoints TEs to face same direction, optionally removing redundancy
        '''Repoints TEs to face same direction, optionally removing redundancy.'''
        try:### ~ [1] Setup ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
            seqlist = rje_seqlist.SeqList(self.log,self.cmd_list+['autoload=T','seqin=%s' % self.getStr('SearchDB')])
            seqdict = seqlist.seqNameDic()
            db = self.obj['DB']
            ldb = self.db('Local')
            gdb = self.db('gablam')
            gdb.dataFormat({'HitLen':'int','QryLen':'int'})
            buffer = self.getInt('MinLength')
            ltrmax = 500

            telen = {}
            hitlen = {}
            for entry in gdb.entries():
                qry = entry['Qry']
                if qry not in telen: telen[qry] = entry['QryLen']
                hit = entry['Hit']
                if hit not in hitlen: hitlen[hit] = entry['HitLen']

            ldb.dataFormat({'AlnNum':'int','BitScore':'num','Expect':'num','Identity':'int','QryStart':'int','QryEnd':'int','SbjStart':'int','SbjEnd':'int','Length':'int'})
            ldb.indexReport('Hit')

            #i# Suffixes and Prefixes for strand and incomplete ends
            ldb.addField('TE')
            for entry in ldb.entries():
                qry = entry['Qry']
                te = rje.matchExp('(Ty\d)',qry)[0]
                full5 = entry['QryStart'] < buffer
                full3 = entry['QryEnd'] > telen[qry] - buffer
                if full3 and entry['Length'] < ltrmax: te += 'LTR2'
                elif full5 and entry['Length'] < ltrmax: te += 'LTR1'
                else:
                    if not full5: te = '<%s' % te
                    if not full3: te = '%s>' % te
                if entry['SbjStart'] > entry['SbjEnd']:
                    (entry['SbjStart'],entry['SbjEnd']) = (entry['SbjEnd'],entry['SbjStart'])
                    entry['TE'] = '-%s' % te
                else:
                    entry['TE'] = '+%s' % te
            #i# The direction of the element is given by +/- at the start of the name
            #i# Start is always before End

            ldb.rename('temap')
            ldb.renameField('SbjStart','Start')
            ldb.renameField('SbjEnd','End')
            ldb.newKey(['Hit','Start','End'])
            ldb.keepFields(['Hit','Start','End','TE'])
            ldb.saveToFile()

            #Merge into composites
            ldb.rename('temerge')
            preventry = {}; prex = ldb.entryNum()
            ldb.addField('ID'); idx = 1
            for entry in ldb.entries(sorted=True):
                entry['ID'] = rje.preZero(idx,prex)
                if not preventry: preventry = entry; continue
                if preventry['Hit'] != entry['Hit']: preventry = {}; continue
                if entry['Start'] - preventry['End'] < buffer:
                    preventry['TE'] = '%s%s' % (preventry['TE'],entry['TE'])
                    preventry['End'] = entry['End']
                    ldb.dropEntry(entry)
                else: preventry = entry
            if prex != ldb.entryNum(): ldb.remakeKeys()
            ldb.newKey(['ID'])

            ldb.saveToFile()

            ### Convert into TE identities plus a counter and extract flanking sequences - merge into composites as we go

            # Extract flanks and search these against the reference proteome to get locations
            #?# What length of sequence should we search? Enough to be unique but not TOO much.
            # Keep best hit for each flank -> Want to use GABLAM unique again.
            #?# RevComp the 5' flank such that we always want hits with Start < buffer?
            teflank = 5000
            flankseq = '%s.teflanks.fas' % self.baseFile()
            FLANKSEQ = open(flankseq,'w')
            for entry in ldb.entries(sorted=True):
                sequence = seqlist.seqSequence(seqdict[entry['Hit']])
                x = max(0,entry['Start']-teflank-1)
                flank5 = rje_sequence.reverseComplement(sequence[x:entry['Start']-1])
                flank3 = sequence[entry['End']:entry['End']+teflank]
                FLANKSEQ.write('>%s.5 %s\n%s\n>%s.3 %s\n%s\n' % (entry['ID'],entry['TE'],flank5,entry['ID'],entry['TE'],flank3))
            FLANKSEQ.close()
            self.printLog('#FLANK','TE flanks output to %s' % flankseq)

            ### Search against refgenome and keep best hits
            gcmd = ['fullblast=T','keepblast=T','fullres=F','hitsum=F','blastp=blastn'] + self.cmd_list
            gcmd += ['local=%s' % self.getBool('KeepLocal'),'localmin=%d' % self.getInt('MinLength'),'localidmin=%f' % self.getNum('MinID')]
            gcmd += ['basefile=%s.teflanks' % self.baseFile(),'localunique=T']
            gcmd += ['searchdb=%s' % flankseq]
            gcmd += ['seqin=%s' % self.getStr('RefGenome')]
            gab = self.obj['GABLAM'] = gablam.GABLAM(self.log,gcmd)
            gab.gablam()
            fdb = gab.obj['BLAST'].db('unique')
            fdb.dataFormat({'AlnID':'int','BitScore':'num','Expect':'num','Identity':'int','QryStart':'int','QryEnd':'int','SbjStart':'int','SbjEnd':'int','Length':'int'})
            if self.getBool('CleanDB'): rje_blast.cleanupDB(self,gab.getStr('SearchDB'))

            ### Combine flank hits with TE hits
            ldb.addField('Flank5',evalue=0)
            ldb.addField('Gap5',evalue=teflank)
            ldb.addField('Flank3',evalue=0)
            ldb.addField('Gap3',evalue=teflank)
            for entry in fdb.entries():
                te = ldb.data(entry['Hit'][:-2])
                start = min(entry['SbjStart'],entry['SbjEnd'])
                x = entry['Hit'][-1]
                if start >= te['Gap%d' % x]: continue
                te['Gap%d' % x] = start - 1
                if entry['SbjStart'] > entry['SbjEnd']:
                    te['Flank%d' % x] = -entry['QryEnd']
                else:
                    te['Flank%d' % x] = entry['QryStart']
            if self.dev():
                ldb.rename('teflank')
                ldb.saveToFile()

            #i# Start is always before End, so Flank5 and Flank3 are relative to original sequence
            #># Should reverse the -ve TEs and swap Flank5 and Flank3
            #i# Note that -ve FlankX values indicate -ve strand hits for that flank BUT Flank5 is on the opposite strand
            ldb.addField('Strand')
            for entry in fdb.entries():
                #i# Change Flank5 to be the same strand as the TE.
                entry['Flank5'] = -entry['Flank5']
                #i# Make the TE strand relative to RefGenome
                #i# First convert all to + TEs
                if entry['TE'][0] == '-':
                    #># Should reverse the -ve TEs and swap Flank5 and Flank3
                    (entry['Flank5'],entry['Flank3']) = (-entry['Flank3'],-entry['Flank5'])
                    (entry['Gap5'],entry['Gap3']) = (-entry['Flank3'],-entry['Gap3'])

                #i# Then identify strand based on +/- Flank values
                #!# No such thing as strand - two ends might be different and on different chromosomes!

                #entry['Strand'] =

            ### Reduce to individual TEs, merging when within a certain distance
            #?# What order should this be done in? TEs can potentially link up differently depending on order
            #i# Calculate a distance between each pair of same kind of TE
            #?# *OR* Merge the 5' positions and 3' positions independently but strand-specifically
            #?# ...ordered by proximity to TE (GapX) and merged based on position+gapx < buffer
            #?# ...then merge TEs with the same 5' and 3' location
            #i# Note: a position of 0 indicates no mapping: do not merge!
            ldb.rename('tehunt')




            self.printLog('#TREX','%s mode not yet fully implemented!' % self.getStrLC('TRex'))
            return True     # Run successful
        except: self.errorLog('Problem during %s huntTE.' % self.prog()); return False  # Failed
#########################################################################################################################
### End of SECTION II: TRex Class                                                                                       #
#########################################################################################################################

                                                    ### ~ ### ~ ###

#########################################################################################################################
### SECTION III: MODULE METHODS                                                                                         #
#########################################################################################################################

#########################################################################################################################
### END OF SECTION III                                                                                                  #
#########################################################################################################################

                                                    ### ~ ### ~ ###

#########################################################################################################################
### SECTION IV: MAIN PROGRAM                                                                                            #
#########################################################################################################################
def runMain():
    ### ~ [1] ~ Basic Setup of Program  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
    try: (info,out,mainlog,cmd_list) = setupProgram()
    except SystemExit: return  
    except: print 'Unexpected error during program setup:', sys.exc_info()[0]; return
    
    ### ~ [2] ~ Rest of Functionality... ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
    try: TRex(mainlog,['dna=T']+cmd_list+['tuplekeys=T']).run()

    ### ~ [3] ~ End ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ###
    except SystemExit: return  # Fork exit etc.
    except KeyboardInterrupt: mainlog.errorLog('User terminated.')
    except: mainlog.errorLog('Fatal error in main %s run.' % info.program)
    mainlog.endLog(info)
#########################################################################################################################
if __name__ == "__main__":      ### Call runMain 
    try: runMain()
    except: print 'Cataclysmic run error:', sys.exc_info()[0]
    sys.exit()
#########################################################################################################################
### END OF SECTION IV                                                                                                   #
#########################################################################################################################
