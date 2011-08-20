# This is a modified version of configobj-py3 by Zubin Mithra (https://bitbucket.org/zubin71/configobj-py3)
# which itself is a Python 3 version of ConfigObj (http://www.voidspace.org.uk/python/configobj.html).
# The difference is mainly that bug https://bitbucket.org/zubin71/configobj-py3/issue/1/expected-an-object-with-the-buffer
# is fixed and that validation, configspec and interpolation stuff that is not needed by OMG was removed.


# configobj.py
# A config file reader/writer that supports nested sections in config files.
# Copyright (C) 2005-2010 Michael Foord, Nicola Larosa
# E-mail: fuzzyman AT voidspace DOT org DOT uk
#         nico AT tekNico DOT net

# ConfigObj 4
# http://www.voidspace.org.uk/python/configobj.html

# Released subject to the BSD License
# Please see http://www.voidspace.org.uk/python/license.shtml

# Scripts maintained at http://www.voidspace.org.uk/python/index.shtml
# For information about bugfixes, updates and support, please join the
# ConfigObj mailing list:
# http://lists.sourceforge.net/lists/listinfo/configobj-develop
# Comments, suggestions and bug reports welcome.

import os
import re
import sys

from codecs import BOM_UTF8, BOM_UTF16, BOM_UTF16_BE, BOM_UTF16_LE

from ast import parse

# A dictionary mapping BOM to
# the encoding to decode with, and what to set the
# encoding attribute to.
BOMS = {
    BOM_UTF8: ('utf_8', None),
    BOM_UTF16_BE: ('utf16_be', 'utf_16'),
    BOM_UTF16_LE: ('utf16_le', 'utf_16'),
    BOM_UTF16: ('utf_16', 'utf_16'),
    }
    
# All legal variants of the BOM codecs.
# TODO: the list of aliases is not meant to be exhaustive, is there a
# better way ?
BOM_LIST = {
    'utf_16': 'utf_16',
    'u16': 'utf_16',
    'utf16': 'utf_16',
    'utf-16': 'utf_16',
    'utf16_be': 'utf16_be',
    'utf_16_be': 'utf16_be',
    'utf-16be': 'utf16_be',
    'utf16_le': 'utf16_le',
    'utf_16_le': 'utf16_le',
    'utf-16le': 'utf16_le',
    'utf_8': 'utf_8',
    'u8': 'utf_8',
    'utf': 'utf_8',
    'utf8': 'utf_8',
    'utf-8': 'utf_8',
    }

# Map of encodings to the BOM to write.
BOM_SET = {
    'utf_8': BOM_UTF8,
    'utf_16': BOM_UTF16,
    'utf16_be': BOM_UTF16_BE,
    'utf16_le': BOM_UTF16_LE,
    None: BOM_UTF8
    }


def match_utf8(encoding):
    return BOM_LIST.get(encoding.lower()) == 'utf_8'

# Quote strings used for writing values
squot = "'%s'"
dquot = '"%s"'
noquot = "%s"
wspace_plus = ' \r\n\v\t\'"'
tsquot = '"""%s"""'
tdquot = "'''%s'''"

# Sentinel for use in getattr calls to replace hasattr
MISSING = object()

__version__ = '4.7.2'


__all__ = (
    '__version__',
    'DEFAULT_INDENT_TYPE',
    'ConfigObjError',
    'NestingError',
    'ParseError',
    'DuplicateError',
    'ConfigObj',
    'SimpleVal',
    'RepeatSectionError',
    'ReloadError',
    'UnreprError',
    'UnknownType',
)

DEFAULT_INDENT_TYPE = '    '

OPTION_DEFAULTS = {
    'raise_errors': False,
    'list_values': True,
    'create_empty': False,
    'file_error': False,
    'stringify': True,
    # option may be set to one of ('', ' ', '\t')
    'indent_type': None,
    'encoding': None,
    'default_encoding': None,
    'unrepr': False,
    'write_empty_values': False,
}

def getObj(s):
    p = parse("a=" + s)
    obj = p.body[0].value
    return obj
    
class UnknownType(Exception):
    pass

class Builder(object):

    def build(self, o):

        m = getattr(self, 'build_' + o.__class__.__name__, None)
        if m is None:
            raise UnknownType(o.__class__.__name__)
        return m(o)

    def build_List(self, o):
        # Modification start
        # Use list(map()) since map returns map objects under Python 3
        return list(map(self.build, o.elts))
        # Modification end
    
    def build_Num(self, o):
        return o.n

    def build_Str(str, o):
        return o.s

    def build_Dict(self, o):
        d = {}
        items = zip(o.keys, o.values)
        for key, value in items:
            key = self.build(key)
            value = self.build(value)
            d[key] = value
        return d

    def build_Tuple(self, o):
        return tuple(self.build_List(o))

    def build_Name(self, o):
        value = o.id
        if value == 'None':
            return None
        if value == 'True':
            return True
        if value == 'False':
            return False

        # An undefined Name
        raise UnknownType('Undefined Name')

_builder = Builder()

def unrepr(s):
    if not s:
        return s
    return _builder.build(getObj(s))
    
    
class ConfigObjError(SyntaxError):
    """
    This is the base class for all errors that ConfigObj raises.
    It is a subclass of SyntaxError.
    """
    def __init__(self, message='', line_number=None, line=''):
        self.line = line
        self.line_number = line_number
        SyntaxError.__init__(self, message)


class NestingError(ConfigObjError):
    """
    This error indicates a level of nesting that doesn't match.
    """


class ParseError(ConfigObjError):
    """
    This error indicates that a line is badly written.
    It is neither a valid ``key = value`` line,
    nor a valid section marker line.
    """


class ReloadError(IOError):
    """
    A 'reload' operation failed.
    This exception is a subclass of ``IOError``.
    """
    def __init__(self):
        IOError.__init__(self, 'reload failed, filename is not set.')


class DuplicateError(ConfigObjError):
    """
    The keyword or section specified already exists.
    """


class RepeatSectionError(ConfigObjError):
    """
    This error indicates additional sections in a section with a
    ``__many__`` (repeated) section.
    """


class UnreprError(ConfigObjError):
    """An error parsing in unrepr mode."""


def __newobj__(cls, *args):
    # Hack for pickle
    return cls.__new__(cls, *args)


class Section(dict):
    """
    A dictionary-like object that represents a section in a config file.

    A Section will behave like an ordered dictionary - following the
    order of the ``scalars`` and ``sections`` attributes.
    You can use this to change the order of members.

    Iteration follows the order: scalars, then sections.
    """

    def __setstate__(self, state):
        dict.update(self, state[0])
        self.__dict__.update(state[1])
    
    def __reduce__(self):
        state = (dict(self), self.__dict__)
        return (__newobj__, (self.__class__,), state)

    def __init__(self, parent, depth, main, indict=None, name=None):
        """
        * parent is the section above
        * depth is the depth level of this section
        * main is the main ConfigObj
        * indict is a dictionary to initialise the section with
        """
        if indict is None:
            indict = {}
        dict.__init__(self)
        # used for nesting level *and* interpolation
        self.parent = parent
        # used for the interpolation attribute
        self.main = main
        # level of nesting depth of this Section
        self.depth = depth
        # purely for information
        self.name = name
        #
        self._initialise()
        # we do this explicitly so that __setitem__ is used properly
        # (rather than just passing to ``dict.__init__``)
        for entry, value in list(indict.items()):
            self[entry] = value

    def _initialise(self):
        # the sequence of scalar values in this Section
        self.scalars = []
        # the sequence of sections in this Section
        self.sections = []
        # for comments :-)
        self.comments = {}
        self.inline_comments = {}
        # for defaults
        self.defaults = []
        self.default_values = {}
        self.extra_values = []
        self._created = False


    def __setitem__(self, key, value, unrepr=False):
        """
        Correctly set a value.
        
        Making dictionary values Section instances.
        (We have to special case 'Section' instances - which are also dicts)
        
        Keys must be strings.
        Values need only be strings (or lists of strings) if
        ``main.stringify`` is set.
        
        ``unrepr`` must be set when setting a value to a dictionary, without
        creating a new sub-section.
        """
        if not isinstance(key, str):
            raise ValueError('The key "%s" is not a string.' % key)
        
        # add the comment
        if key not in self.comments:
            self.comments[key] = []
            self.inline_comments[key] = ''
        # remove the entry from defaults
        if key in self.defaults:
            self.defaults.remove(key)
        #
        if isinstance(value, Section):
            if key not in self:
                self.sections.append(key)
            dict.__setitem__(self, key, value)
        elif isinstance(value, dict) and not unrepr:
            # First create the new depth level,
            # then create the section
            if key not in self:
                self.sections.append(key)
            new_depth = self.depth + 1
            dict.__setitem__(
                self,
                key,
                Section(
                    self,
                    new_depth,
                    self.main,
                    indict=value,
                    name=key))
        else:
            if key not in self:
                self.scalars.append(key)
            if not self.main.stringify:
                if isinstance(value, str):
                    pass
                elif isinstance(value, (list, tuple)):
                    for entry in value:
                        if not isinstance(entry, str):
                            raise TypeError('Value is not a string "%s".' % entry)
                else:
                    raise TypeError('Value is not a string "%s".' % value)
            dict.__setitem__(self, key, value)


    def __delitem__(self, key):
        """Remove items from the sequence when deleting."""
        dict. __delitem__(self, key)
        if key in self.scalars:
            self.scalars.remove(key)
        else:
            self.sections.remove(key)
        del self.comments[key]
        del self.inline_comments[key]


    def update(self, indict):
        """
        A version of update that uses our ``__setitem__``.
        """
        for entry in indict:
            self[entry] = indict[entry]


    def pop(self, key, default=MISSING):
        """
        'D.pop(k[,d]) -> v, remove specified key and return the corresponding value.
        If key is not found, d is returned if given, otherwise KeyError is raised'
        """
        try:
            val = self[key]
        except KeyError:
            if default is MISSING:
                raise
            val = default
        else:
            del self[key]
        return val

    def popitem(self):
        """Pops the first (key,val)"""
        sequence = (self.scalars + self.sections)
        if not sequence:
            raise KeyError(": 'popitem(): dictionary is empty'")
        key = sequence[0]
        val =  self[key]
        del self[key]
        return key, val
    
    def clear(self):
        """
        A version of clear that also affects scalars/sections
        Also clears comments and configspec.
        
        Leaves other attributes alone :
            depth/main/parent are not affected
        """
        dict.clear(self)
        self.scalars = []
        self.sections = []
        self.comments = {}
        self.inline_comments = {}
        self.defaults = []
        self.extra_values = []


    def setdefault(self, key, default=None):
        """A version of setdefault that sets sequence if appropriate."""
        try:
            return self[key]
        except KeyError:
            self[key] = default
            return self[key]


    def items(self):
        """D.items() -> list of D's (key, value) pairs, as 2-tuples"""
        return list(zip((self.scalars + self.sections), list(self.values())))


    def keys(self):
        """D.keys() -> list of D's keys"""
        return (self.scalars + self.sections)


    def values(self):
        """D.values() -> list of D's values"""
        return [self[key] for key in (self.scalars + self.sections)]


    def iteritems(self):
        """D.iteritems() -> an iterator over the (key, value) items of D"""
        return iter(list(self.items()))


    def iterkeys(self):
        """D.iterkeys() -> an iterator over the keys of D"""
        return iter((self.scalars + self.sections))

    __iter__ = iterkeys


    def itervalues(self):
        """D.itervalues() -> an iterator over the values of D"""
        return iter(list(self.values()))


    def __repr__(self):
        """x.__repr__() <==> repr(x)"""
        return '{%s}' % ', '.join([('%s: %s' % (repr(key), repr(self[key])))
            for key in (self.scalars + self.sections)])

    __str__ = __repr__
    __str__.__doc__ = "x.__str__() <==> str(x)"


    # Extra methods - not in a normal dictionary

    def dict(self):
        """
        Return a deepcopy of self as a dictionary.
        
        All members that are ``Section`` instances are recursively turned to
        ordinary dictionaries - by calling their ``dict`` method.
        
        >>> n = a.dict()
        >>> n == a
        1
        >>> n is a
        0
        """
        newdict = {}
        for entry in self:
            this_entry = self[entry]
            if isinstance(this_entry, Section):
                this_entry = this_entry.dict()
            elif isinstance(this_entry, list):
                # create a copy rather than a reference
                this_entry = list(this_entry)
            elif isinstance(this_entry, tuple):
                # create a copy rather than a reference
                this_entry = tuple(this_entry)
            newdict[entry] = this_entry
        return newdict

    
    def as_bool(self, key):
        """
        Accepts a key as input. The corresponding value must be a string or
        the objects (``True`` or 1) or (``False`` or 0). We allow 0 and 1 to
        retain compatibility with Python 2.2.
        
        If the string is one of  ``True``, ``On``, ``Yes``, or ``1`` it returns 
        ``True``.
        
        If the string is one of  ``False``, ``Off``, ``No``, or ``0`` it returns 
        ``False``.
        
        ``as_bool`` is not case sensitive.
        
        Any other input will raise a ``ValueError``.
        
        >>> a = ConfigObj()
        >>> a['a'] = 'fish'
        >>> a.as_bool('a')
        Traceback (most recent call last):
        ValueError: Value "fish" is neither True nor False
        >>> a['b'] = 'True'
        >>> a.as_bool('b')
        1
        >>> a['b'] = 'off'
        >>> a.as_bool('b')
        0
        """
        val = self[key]
        if val == True:
            return True
        elif val == False:
            return False
        else:
            try:
                if not isinstance(val, str):
                    # TODO: Why do we raise a KeyError here?
                    raise KeyError()
                else:
                    return self.main._bools[val.lower()]
            except KeyError:
                raise ValueError('Value "%s" is neither True nor False' % val)
    
    def as_int(self, key):
        """
        A convenience method which coerces the specified value to an integer.
        
        If the value is an invalid literal for ``int``, a ``ValueError`` will
        be raised.
        
        >>> a = ConfigObj()
        >>> a['a'] = 'fish'
        >>> a.as_int('a')
        Traceback (most recent call last):
        ValueError: invalid literal for int() with base 10: 'fish'
        >>> a['b'] = '1'
        >>> a.as_int('b')
        1
        >>> a['b'] = '3.2'
        >>> a.as_int('b')
        Traceback (most recent call last):
        ValueError: invalid literal for int() with base 10: '3.2'
        """
        return int(self[key])
    
    def as_float(self, key):
        """
        A convenience method which coerces the specified value to a float.

        If the value is an invalid literal for ``float``, a ``ValueError`` will
        be raised.

        >>> a = ConfigObj()
        >>> a['a'] = 'fish'
        >>> a.as_float('a')
        Traceback (most recent call last):
        ValueError: invalid literal for float(): fish
        >>> a['b'] = '1'
        >>> a.as_float('b')
        1.0
        >>> a['b'] = '3.2'
        >>> a.as_float('b')
        3.2000000000000002
        """
        return float(self[key])

    def as_list(self, key):
        """
        A convenience method which fetches the specified value, guaranteeing
        that it is a list.

        >>> a = ConfigObj()
        >>> a['a'] = 1
        >>> a.as_list('a')
        [1]
        >>> a['a'] = (1,)
        >>> a.as_list('a')
        [1]
        >>> a['a'] = [1]
        >>> a.as_list('a')
        [1]
        """
        result = self[key]
        if isinstance(result, (tuple, list)):
            return list(result)
        return [result]


class ConfigObj(Section):
    """An object to read, create, and write config files."""

    _keyword = re.compile(r'''^ # line start
        (\s*)                   # indentation
        (                       # keyword
            (?:".*?")|          # double quotes
            (?:'.*?')|          # single quotes
            (?:[^'"=].*?)       # no quotes
        )
        \s*=\s*                 # divider
        (.*)                    # value (including list values and comments)
        $   # line end
        ''',
        re.VERBOSE)

    _sectionmarker = re.compile(r'''^
        (\s*)                     # 1: indentation
        ((?:\[\s*)+)              # 2: section marker open
        (                         # 3: section name open
            (?:"\s*\S.*?\s*")|    # at least one non-space with double quotes
            (?:'\s*\S.*?\s*')|    # at least one non-space with single quotes
            (?:[^'"\s].*?)        # at least one non-space unquoted
        )                         # section name close
        ((?:\s*\])+)              # 4: section marker close
        \s*(\#.*)?                # 5: optional comment
        $''',
        re.VERBOSE)

    # this regexp pulls list values out as a single string
    # or single values and comments
    # FIXME: this regex adds a '' to the end of comma terminated lists
    #   workaround in ``_handle_value``
    _valueexp = re.compile(r'''^
        (?:
            (?:
                (
                    (?:
                        (?:
                            (?:".*?")|              # double quotes
                            (?:'.*?')|              # single quotes
                            (?:[^'",\#][^,\#]*?)    # unquoted
                        )
                        \s*,\s*                     # comma
                    )*      # match all list items ending in a comma (if any)
                )
                (
                    (?:".*?")|                      # double quotes
                    (?:'.*?')|                      # single quotes
                    (?:[^'",\#\s][^,]*?)|           # unquoted
                    (?:(?<!,))                      # Empty value
                )?          # last item in a list - or string value
            )|
            (,)             # alternatively a single comma - empty list
        )
        \s*(\#.*)?          # optional comment
        $''',
        re.VERBOSE)

    # use findall to get the members of a list value
    _listvalueexp = re.compile(r'''
        (
            (?:".*?")|          # double quotes
            (?:'.*?')|          # single quotes
            (?:[^'",\#]?.*?)       # unquoted
        )
        \s*,\s*                 # comma
        ''',
        re.VERBOSE)

    # this regexp is used for the value
    # when lists are switched off
    _nolistvalue = re.compile(r'''^
        (
            (?:".*?")|          # double quotes
            (?:'.*?')|          # single quotes
            (?:[^'"\#].*?)|     # unquoted
            (?:)                # Empty value
        )
        \s*(\#.*)?              # optional comment
        $''',
        re.VERBOSE)

    # regexes for finding triple quoted values on one line
    _single_line_single = re.compile(r"^'''(.*?)'''\s*(#.*)?$")
    _single_line_double = re.compile(r'^"""(.*?)"""\s*(#.*)?$')
    _multi_line_single = re.compile(r"^(.*?)'''\s*(#.*)?$")
    _multi_line_double = re.compile(r'^(.*?)"""\s*(#.*)?$')

    _triple_quote = {
        "'''": (_single_line_single, _multi_line_single),
        '"""': (_single_line_double, _multi_line_double),
    }

    # Used by the ``istrue`` Section method
    _bools = {
        'yes': True, 'no': False,
        'on': True, 'off': False,
        '1': True, '0': False,
        'true': True, 'false': False,
        }

    def __init__(self, infile=None, options=None, encoding=None,
                 raise_errors=False, list_values=True,
                 create_empty=False, file_error=False, stringify=True,
                 indent_type=None, default_encoding=None, unrepr=False,
                 write_empty_values=False):
        """
        Parse a config file or create a config file object.
        
        ``ConfigObj(infile=None, encoding=None,
                    raise_errors=False, list_values=True,
                    create_empty=False, file_error=False, stringify=True,
                    indent_type=None, default_encoding=None, unrepr=False,
                    write_empty_values=False)``
        """
        # init the superclass
        Section.__init__(self, self, 0, self)
        
        infile = infile or []
        
        _options = {'encoding': encoding,
                    'raise_errors': raise_errors, 'list_values': list_values,
                    'create_empty': create_empty, 'file_error': file_error,
                    'stringify': stringify, 'indent_type': indent_type,
                    'default_encoding': default_encoding, 'unrepr': unrepr,
                    'write_empty_values': write_empty_values}

        if options is None:
            options = _options
        else:
            import warnings
            warnings.warn('Passing in an options dictionary to ConfigObj() is '
                          'deprecated. Use **options instead.',
                          DeprecationWarning, stacklevel=2)
            
            # TODO: check the values too.
            for entry in options:
                if entry not in OPTION_DEFAULTS:
                    raise TypeError('Unrecognised option "%s".' % entry)
            for entry, value in list(OPTION_DEFAULTS.items()):
                if entry not in options:
                    options[entry] = value
                keyword_value = _options[entry]
                if value != keyword_value:
                    options[entry] = keyword_value

        
        self._initialise(options)
        self._load(infile)
    
    def _load(self, infile):

        if isinstance(infile, str):
            self.filename = infile
            if os.path.isfile(infile):
                h = open(infile, 'rb')
                infile = h.read() or []
                h.close()
            elif self.file_error:
                # raise an error if the file doesn't exist
                raise IOError('Config file not found: "%s".' % self.filename)
            else:
                # file doesn't already exist
                if self.create_empty:
                    # this is a good test that the filename specified
                    # isn't impossible - like on a non-existent device
                    h = open(infile, 'w')
                    h.write('')
                    h.close()
                infile = []        
        elif isinstance(infile, (list, tuple)):
            infile = list(infile)
        elif isinstance(infile, dict):
            # initialise self
            # the Section class handles creating subsections
            if isinstance(infile, ConfigObj):
                # get a copy of our ConfigObj
                def set_section(in_section, this_section):
                    for entry in in_section.scalars:
                        this_section[entry] = in_section[entry]
                    for section in in_section.sections:
                        this_section[section] = {}
                        set_section(in_section[section], this_section[section])
                set_section(infile, self)
                
            else:
                for entry in infile:
                    self[entry] = infile[entry]
            del self._errors
            return
        
        elif getattr(infile, 'read', MISSING) is not MISSING:
            # This supports file like objects
            infile = infile.read() or []
            # needs splitting into lines - but needs doing *after* decoding
            # in case it's not an 8 bit encoding
        else:
            raise TypeError('infile must be a filename, file like object, or list of lines.')
        
        if infile:
            # don't do it for the empty ConfigObj
            infile = self._handle_bom(infile)
            # infile is now *always* a list
            #
            # Set the newlines attribute (first line ending it finds)
            # and strip trailing '\n' or '\r' from lines
            for line in infile:
                if (not line) or (line[-1] not in ('\r', '\n', '\r\n')):
                    continue
                for end in ('\r\n', '\n', '\r'):
                    if line.endswith(end):
                        self.newlines = end
                        break
                break

            infile = [line.rstrip('\r\n') for line in infile]

            
        self._parse(infile)
        # if we had any errors, now is the time to raise them
        if self._errors:
            info = "at line %s." % self._errors[0].line_number
            if len(self._errors) > 1:
                msg = "Parsing failed with several errors.\nFirst error %s" % info
                error = ConfigObjError(msg)
            else:
                error = self._errors[0]
            # set the errors attribute; it's a list of tuples:
            # (error_type, message, line_number)
            error.errors = self._errors
            # set the config attribute
            error.config = self
            raise error
        # delete private attributes
        del self._errors
    
    def _initialise(self, options=None):
        if options is None:
            options = OPTION_DEFAULTS
            
        # initialise a few variables
        self.filename = None
        self._errors = []
        self.raise_errors = options['raise_errors']
        self.list_values = options['list_values']
        self.create_empty = options['create_empty']
        self.file_error = options['file_error']
        self.stringify = options['stringify']
        self.indent_type = options['indent_type']
        self.encoding = options['encoding']
        self.default_encoding = options['default_encoding']
        self.BOM = False
        self.newlines = None
        self.write_empty_values = options['write_empty_values']
        self.unrepr = options['unrepr']
        
        self.initial_comment = []
        self.final_comment = []
        
        # Clear section attributes as well
        Section._initialise(self)
    
    def __repr__(self):
        def _getval(key):
            try:
                return self[key]
            except MissingInterpolationOption:
                return dict.__getitem__(self, key)
        return ('ConfigObj({%s})' % 
                ', '.join([('%s: %s' % (repr(key), repr(_getval(key)))) 
                for key in (self.scalars + self.sections)]))
    
    def _handle_bom(self, infile):
        """
        Handle any BOM, and decode if necessary.
        
        If an encoding is specified, that *must* be used - but the BOM should
        still be removed (and the BOM attribute set).
        
        (If the encoding is wrongly specified, then a BOM for an alternative
        encoding won't be discovered or removed.)
        
        If an encoding is not specified, UTF8 or UTF16 BOM will be detected and
        removed. The BOM attribute will be set. UTF16 will be decoded to
        unicode.
        
        NOTE: This method must not be called with an empty ``infile``.
        
        Specifying the *wrong* encoding is likely to cause a
        ``UnicodeDecodeError``.
        
        ``infile`` must always be returned as a list of lines, but may be
        passed in as a single string.
        """
        if ((self.encoding is not None) and
            (self.encoding.lower() not in BOM_LIST)):
            # No need to check for a BOM
            # the encoding specified doesn't have one
            # just decode
            return self._decode(infile, self.encoding)
        
        if isinstance(infile, (list, tuple)):
            line = infile[0]
        else:
            line = infile
        if self.encoding is not None:
            # encoding explicitly supplied
            # And it could have an associated BOM
            # TODO: if encoding is just UTF16 - we ought to check for both
            # TODO: big endian and little endian versions.
            enc = BOM_LIST[self.encoding.lower()]
            if enc == 'utf_16':
                # For UTF16 we try big endian and little endian
                for BOM, (encoding, final_encoding) in list(BOMS.items()):
                    if not final_encoding:
                        # skip UTF8
                        continue
                    if isinstance(infile, bytes) and infile.startswith(BOM):
                        ### BOM discovered
                        ##self.BOM = True
                        # Don't need to remove BOM
                        return self._decode(infile, encoding)
                    
                # If we get this far, will *probably* raise a DecodeError
                # As it doesn't appear to start with a BOM
                return self._decode(infile, self.encoding)
            
            # Must be UTF8
            BOM = BOM_SET[enc]
            if isinstance(line, bytes) and not line.startswith(BOM):
                return self._decode(infile, self.encoding)
            
            newline = line[len(BOM):]
            
            # BOM removed
            if isinstance(infile, (list, tuple)):
                infile[0] = newline
            else:
                infile = newline
            self.BOM = True
            return self._decode(infile, self.encoding)
        
        # No encoding specified - so we need to check for UTF8/UTF16
        for BOM, (encoding, final_encoding) in list(BOMS.items()):
            if isinstance(line, bytes) and not line.startswith(BOM):
                continue
            else:
                # BOM discovered
                # self.encoding = final_encoding
                if not final_encoding:
                    self.BOM = True
                    # UTF8
                    # remove BOM
                    newline = line[len(BOM):]
                    if isinstance(infile, (list, tuple)):
                        infile[0] = newline
                    else:
                        infile = newline
                    # UTF8 - don't decode
                    if isinstance(infile, str):
                        return infile.splitlines(True)
                    else:
                        return infile
                
                infile = self._decode(infile, encoding)
                if isinstance(infile, str):
                    # infile read from a file will be a single string
                    return infile.splitlines(True)
                return self._decode(infile, encoding)
                # UTF16 - have to decode

            
        # No BOM discovered and no encoding specified, just return
        if isinstance(infile, str):
            # infile read from a file will be a single string
            return infile.splitlines(True)
        
        if isinstance(infile, bytes):
            return self._decode(infile, self.encoding)
        return infile

    def _decode(self, infile, encoding):
        """
        Decode infile to unicode. Using the specified encoding.

        if is a string, it also needs converting to a list.
        """
        
        encoding = encoding or 'utf-8'
        
        # If `infile` is a Unicode string, return as such
        if isinstance(infile, str):
            return infile
            
        # If `infile` is bytes type; decode and split
        if isinstance(infile, bytes):
            return infile.decode(encoding).splitlines(True)

        # If `infile` is a mix of bytes and unicode strings
        for i, line in enumerate(infile):
            if isinstance(line, bytes):
                infile[i] = line.decode(encoding)
        return infile
    
    def _decode_element(self, line):
        """Decode element to unicode if necessary."""
        if not self.encoding:
            return line
        if isinstance(line, bytes) and self.default_encoding:
            return line.decode(self.default_encoding)
        return line


    def _parse(self, infile):
        """Actually parse the config file."""
        
        temp_list_values = self.list_values
        if self.unrepr:
            self.list_values = False
            
        comment_list = []
        done_start = False
        this_section = self
        maxline = len(infile) - 1
        cur_index = -1
        reset_comment = False
        
        while cur_index < maxline:
            if reset_comment:
                comment_list = []
            cur_index += 1
            line = infile[cur_index]
            sline = line.strip()
            # do we have anything on the line ?
            if not sline or sline.startswith('#'):
                reset_comment = False
                comment_list.append(line)
                continue
            
            if not done_start:
                # preserve initial comment
                self.initial_comment = comment_list
                comment_list = []
                done_start = True
                
            reset_comment = True
            # first we check if it's a section marker
            mat = self._sectionmarker.match(line)
            if mat is not None:
                # is a section line
                (indent, sect_open, sect_name, sect_close, comment) = mat.groups()
                if indent and (self.indent_type is None):
                    self.indent_type = indent
                cur_depth = sect_open.count('[')
                if cur_depth != sect_close.count(']'):
                    self._handle_error("Cannot compute the section depth at line %s.",
                                       NestingError, infile, cur_index)
                    continue
                
                if cur_depth < this_section.depth:
                    # the new section is dropping back to a previous level
                    try:
                        parent = self._match_depth(this_section,
                                                   cur_depth).parent
                    except SyntaxError:
                        self._handle_error("Cannot compute nesting level at line %s.",
                                           NestingError, infile, cur_index)
                        continue
                elif cur_depth == this_section.depth:
                    # the new section is a sibling of the current section
                    parent = this_section.parent
                elif cur_depth == this_section.depth + 1:
                    # the new section is a child the current section
                    parent = this_section
                else:
                    self._handle_error("Section too nested at line %s.",
                                       NestingError, infile, cur_index)
                    
                sect_name = self._unquote(sect_name)
                if sect_name in parent:
                    self._handle_error('Duplicate section name at line %s.',
                                       DuplicateError, infile, cur_index)
                    continue
                
                # create the new section
                this_section = Section(
                    parent,
                    cur_depth,
                    self,
                    name=sect_name)
                parent[sect_name] = this_section
                parent.inline_comments[sect_name] = comment
                parent.comments[sect_name] = comment_list
                continue
            #
            # it's not a section marker,
            # so it should be a valid ``key = value`` line
            mat = self._keyword.match(line)
            if mat is None:
                # it neither matched as a keyword
                # or a section marker
                self._handle_error(
                    'Invalid line at line "%s".',
                    ParseError, infile, cur_index)
            else:
                # is a keyword value
                # value will include any inline comment
                (indent, key, value) = mat.groups()
                if indent and (self.indent_type is None):
                    self.indent_type = indent
                # check for a multiline value
                if value[:3] in ['"""', "'''"]:
                    try:
                        value, comment, cur_index = self._multiline(
                            value, infile, cur_index, maxline)
                    except SyntaxError:
                        self._handle_error(
                            'Parse error in value at line %s.',
                            ParseError, infile, cur_index)
                        continue
                    else:
                        if self.unrepr:
                            comment = ''
                            try:
                                value = unrepr(value)
                            except Exception as e:
                                if type(e) == UnknownType:
                                    msg = 'Unknown name or type in value at line %s.'
                                else:
                                    msg = 'Parse error in value at line %s.'
                                self._handle_error(msg, UnreprError, infile,
                                    cur_index)
                                continue
                else:
                    if self.unrepr:
                        comment = ''
                        try:
                            value = unrepr(value)
                        except Exception as e:
                            if isinstance(e, UnknownType):
                                msg = 'Unknown name or type in value at line %s.'
                            else:
                                msg = 'Parse error in value at line %s.'
                            self._handle_error(msg, UnreprError, infile,
                                cur_index)
                            continue
                    else:
                        # extract comment and lists
                        try:
                            (value, comment) = self._handle_value(value)
                        except SyntaxError:
                            self._handle_error(
                                'Parse error in value at line %s.',
                                ParseError, infile, cur_index)
                            continue
                #
                key = self._unquote(key)
                if key in this_section:
                    self._handle_error(
                        'Duplicate keyword name at line %s.',
                        DuplicateError, infile, cur_index)
                    continue
                # add the key.
                # we set unrepr because if we have got this far we will never
                # be creating a new section
                this_section.__setitem__(key, value, unrepr=True)
                this_section.inline_comments[key] = comment
                this_section.comments[key] = comment_list
                continue
        #
        if self.indent_type is None:
            # no indentation used, set the type accordingly
            self.indent_type = ''

        # preserve the final comment
        if not self and not self.initial_comment:
            self.initial_comment = comment_list
        elif not reset_comment:
            self.final_comment = comment_list
        self.list_values = temp_list_values
    
    def _match_depth(self, sect, depth):
        """
        Given a section and a depth level, walk back through the sections
        parents to see if the depth level matches a previous section.
        
        Return a reference to the right section,
        or raise a SyntaxError.
        """
        while depth < sect.depth:
            if sect is sect.parent:
                # we've reached the top level already
                raise SyntaxError()
            sect = sect.parent
        if sect.depth == depth:
            return sect
        # shouldn't get here
        raise SyntaxError()
    
    def _handle_error(self, text, ErrorClass, infile, cur_index):
        """
        Handle an error according to the error settings.
        
        Either raise the error or store it.
        The error will have occured at ``cur_index``
        """
        line = infile[cur_index]
        cur_index += 1
        message = text % cur_index
        error = ErrorClass(message, cur_index, line)
        if self.raise_errors:
            # raise the error - parsing stops here
            raise error
        # store the error
        # reraise when parsing has finished
        self._errors.append(error)
    
    def _unquote(self, value):
        """Return an unquoted version of a value"""
        if not value:
            # should only happen during parsing of lists
            raise SyntaxError
        if (value[0] == value[-1]) and (value[0] in ('"', "'")):
            value = value[1:-1]
        return value
    
    def _quote(self, value, multiline=True):
        """
        Return a safely quoted version of a value.

        Raise a ConfigObjError if the value cannot be safely quoted.
        If multiline is ``True`` (default) then use triple quotes
        if necessary.

        * Don't quote values that don't need it.
        * Recursively quote members of a list and return a comma joined list.
        * Multiline is ``False`` for lists.
        * Obey list syntax for empty and single member lists.

        If ``list_values=False`` then the value is only quoted if it contains
        a ``\\n`` (is multiline) or '#'.

        If ``write_empty_values`` is set, and the value is an empty string, it
        won't be quoted.
        """
        if multiline and self.write_empty_values and value == '':
            # Only if multiline is set, so that it is used for values not
            # keys, and not values that are part of a list
            return ''

        if multiline and isinstance(value, (list, tuple)):
            if not value:
                return ','
            elif len(value) == 1:
                return self._quote(value[0], multiline=False) + ','
            return ', '.join([self._quote(val, multiline=False)
                for val in value])
        if not isinstance(value, str):
            if self.stringify and not isinstance(value, bytes):
                value = str(value)
            else:
                raise TypeError('Value "%s" is not a string.' % value)

        if not value:
            return '""'

        no_lists_no_quotes = not self.list_values and '\n' not in value and '#' not in value
        need_triple = multiline and ((("'" in value) and ('"' in value)) or ('\n' in value ))
        hash_triple_quote = multiline and not need_triple and ("'" in value) and ('"' in value) and ('#' in value)
        check_for_single = (no_lists_no_quotes or not need_triple) and not hash_triple_quote

        if check_for_single:
            if not self.list_values:
                # we don't quote if ``list_values=False``
                quot = noquot
            # for normal values either single or double quotes will do
            elif '\n' in value:
                # will only happen if multiline is off - e.g. '\n' in key
                raise ConfigObjError('Value "%s" cannot be safely quoted.' % value)
            elif ((value[0] not in wspace_plus) and
                    (value[-1] not in wspace_plus) and
                    (',' not in value)):
                quot = noquot
            else:
                quot = self._get_single_quote(value)
        else:
            # if value has '\n' or "'" *and* '"', it will need triple quotes
            quot = self._get_triple_quote(value)

        if quot == noquot and '#' in value and self.list_values:
            quot = self._get_single_quote(value)

        return quot % value

    def _get_single_quote(self, value):
        if ("'" in value) and ('"' in value):
            raise ConfigObjError('Value "%s" cannot be safely quoted.' % value)
        elif '"' in value:
            quot = squot
        else:
            quot = dquot
        return quot

    def _get_triple_quote(self, value):
        if (value.find('"""') != -1) and (value.find("'''") != -1):
            raise ConfigObjError('Value "%s" cannot be safely quoted.' % value)
        if value.find('"""') == -1:
            quot = tdquot
        else:
            quot = tsquot 
        return quot

    def _handle_value(self, value):
        """
        Given a value string, unquote, remove comment,
        handle lists. (including empty and single member lists)
        """
        # do we look for lists in values ?
        if not self.list_values:
            mat = self._nolistvalue.match(value)
            if mat is None:
                raise SyntaxError()
            # NOTE: we don't unquote here
            return mat.groups()
        #
        mat = self._valueexp.match(value)
        if mat is None:
            # the value is badly constructed, probably badly quoted,
            # or an invalid list
            raise SyntaxError()
        (list_values, single, empty_list, comment) = mat.groups()
        if (list_values == '') and (single is None):
            # change this if you want to accept empty values
            raise SyntaxError()
        # NOTE: note there is no error handling from here if the regex
        # is wrong: then incorrect values will slip through
        if empty_list is not None:
            # the single comma - meaning an empty list
            return ([], comment)
        if single is not None:
            # handle empty values
            if list_values and not single:
                # FIXME: the '' is a workaround because our regex now matches
                #   '' at the end of a list if it has a trailing comma
                single = None
            else:
                single = single or '""'
                single = self._unquote(single)
        if list_values == '':
            # not a list value
            return (single, comment)
        the_list = self._listvalueexp.findall(list_values)
        the_list = [self._unquote(val) for val in the_list]
        if single is not None:
            the_list += [single]
        return (the_list, comment)

    def _multiline(self, value, infile, cur_index, maxline):
        """Extract the value, where we are in a multiline situation."""
        quot = value[:3]
        newvalue = value[3:]
        single_line = self._triple_quote[quot][0]
        multi_line = self._triple_quote[quot][1]
        mat = single_line.match(value)
        if mat is not None:
            retval = list(mat.groups())
            retval.append(cur_index)
            return retval
        elif newvalue.find(quot) != -1:
            # somehow the triple quote is missing
            raise SyntaxError()
        #
        while cur_index < maxline:
            cur_index += 1
            newvalue += '\n'
            line = infile[cur_index]
            if line.find(quot) == -1:
                newvalue += line
            else:
                # end of multiline, process it
                break
        else:
            # we've got to the end of the config, oops...
            raise SyntaxError()
        mat = multi_line.match(line)
        if mat is None:
            # a badly formed line
            raise SyntaxError()
        (value, comment) = mat.groups()
        return (newvalue + value, comment, cur_index)



    def _write_line(self, indent_string, entry, this_entry, comment):
        """Write an individual line, for the write method"""
        # NOTE: the calls to self._quote here handles non-StringType values.
        if not self.unrepr:
            val = self._decode_element(self._quote(this_entry))
        else:
            val = repr(this_entry)
        return '%s%s%s%s%s' % (indent_string,
                               self._decode_element(self._quote(entry, multiline=False)),
                               ' = ',
                               val,
                               self._decode_element(comment))

    def _write_marker(self, indent_string, depth, entry, comment):
        """Write a section marker line"""
        return '%s%s%s%s%s' % (indent_string,
                               '[' * depth,
                               self._quote(self._decode_element(entry), multiline=False),
                               ']' * depth,
                               self._decode_element(comment))
    
    def _handle_comment(self, comment):
        """Deal with a comment."""
        if not comment:
            return ''
        start = self.indent_type
        if not comment.startswith('#'):
            start += ' # '
        return (start + comment)

    # Public methods

    def write(self, outfile=None, section=None):
        """
        Write the current ConfigObj as a file
        
        tekNico: FIXME: use StringIO instead of real files
        
        >>> filename = a.filename
        >>> a.filename = 'test.ini'
        >>> a.write()
        >>> a.filename = filename
        >>> a == ConfigObj('test.ini', raise_errors=True)
        1
        >>> import os
        >>> os.remove('test.ini')
        """
        if self.indent_type is None:
            # this can be true if initialised from a dictionary
            self.indent_type = DEFAULT_INDENT_TYPE
            
        out = []
        cs = '#'
        csp = '# '
        if section is None:
            section = self
            for line in self.initial_comment:
                line = self._decode_element(line)
                stripped_line = line.strip()
                if stripped_line and not stripped_line.startswith(cs):
                    line = csp + line
                out.append(line)
                
        indent_string = self.indent_type * section.depth
        for entry in (section.scalars + section.sections):
            if entry in section.defaults:
                # don't write out default values
                continue
            for comment_line in section.comments[entry]:
                comment_line = self._decode_element(comment_line.lstrip())
                if comment_line and not comment_line.startswith(cs):
                    comment_line = csp + comment_line
                out.append(indent_string + comment_line)
            this_entry = section[entry]
            comment = self._handle_comment(section.inline_comments[entry])
            
            if isinstance(this_entry, Section):
                # MODIFICATION
                if len(this_entry) > 0 or len(comment) > 0: # Do not write empty sections
                    # END MODIFICATION
                    # a section
                    out.append(self._write_marker(
                        indent_string,
                        this_entry.depth,
                        entry,
                        comment))
                    out.extend(self.write(section=this_entry))
            else:
                out.append(self._write_line(
                    indent_string,
                    entry,
                    this_entry,
                    comment))
                
        if section is self:
            for line in self.final_comment:
                line = self._decode_element(line)
                stripped_line = line.strip()
                if stripped_line and not stripped_line.startswith(cs):
                    line = csp + line
                out.append(line)
            
        if section is not self:
            return out
        
        if (self.filename is None) and (outfile is None):
            
            # output a list of lines
            # might need to encode
            # NOTE: This will *screw* UTF16, each line will start with the BOM
            if self.encoding:
                out = [l.encode(self.encoding) for l in out]
            if (self.BOM and ((self.encoding is None) or
                (BOM_LIST.get(self.encoding.lower()) == 'utf_8'))):
                # Add the UTF8 BOM
                if not out:
                    out.append('')
                out[0] = BOM_UTF8 + out[0]
            return out
            
        
        # Turn the list to a string, joined with correct newlines
        newline = self.newlines or os.linesep
        if (getattr(outfile, 'mode', None) is not None and outfile.mode == 'w'
            and sys.platform == 'win32' and newline == '\r\n'):
            # Windows specific hack to avoid writing '\r\r\n'
            newline = '\n'
        output = newline.join(out)
        
        ###### modification ############
        if not output.endswith(newline):
            output += newline

        # encoding the data to bytes
        if self.encoding:
            output = output.encode(self.encoding)
        else: output = output.encode()
            
        if self.BOM and ((self.encoding is None) or match_utf8(self.encoding)):
            # Add the UTF8 BOM
            output = BOM_UTF8 + output
              
        #if not output.endswith(newline):
        #    output += newline
        if outfile is not None:
            outfile.write(output)
        else:
            h = open(self.filename, 'wb')
            h.write(output)
            h.close()
