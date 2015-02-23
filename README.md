Maestro – Music Managing and Playing Application
================================================

Maestro is a sophisticated music manager that helps you to organize, browse and play your digital music collection.
It is optimized for large collections that consist of a mixture of classical and modern tracks, allowing to efficiently
browse and search through your collection while presenting the results in a structured way.

More information can be found on Maestro website https://github.com/maestromusic/maestro

Maestro is copyright of [Martin Altmayer](martin.altmayer@web.de) and [Michael Helmling](michaelhelmling@posteo.de) and licensed under the GPL v3 (confer the `LICENSE` file).

INSTALLATION
============
Download and extract the current repository snapshot and run

# python3 setup.py install

If you want to install Maestro as normal user inside your home directory, run

$ python3 setup.py install --user

DEVELOPMENT
=============
To contribute in development, get the current HEAD from the git repository:

git clone https://github.com/maestromusic/maestro.git

In order to get a working copy of the current development status, use the command

python setup.py develop --user

which will install an Egg-link inside your ~/.local/lib/python3.x folder, pointing to the git checkout. If
you use the "develop" mode instead in some directory which is not in your normal PYTHONPATH, e.g.

python setup.py develop -d ~/python-stage

you can simultaneously work with an installed version of Maestro.



ATTRIBUTIONS
============

Maestro uses icons from the following software / free icon sets:
Tango       http://tango.freedesktop.org/            released as public domain.
Silk        http://www.famfamfam.com/lab/icons/silk/ by Mark James licensed under CC BY 3.0.
Fugue Icons http://p.yusukekamiyamane.com/           by Yusuke Kamiyamane licensed under CC BY 3.0.
Amarok      http://amarok.kde.org/                   licensed under GPL v3.

Maestro uses some code (VolumeButton, TimeSlider) of [Amarok 2.7.1](http://amarok.kde.org/) licensed under GPL v3.
