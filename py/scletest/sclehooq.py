#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Ce module définit principalement la classe :class:`ScleHooqClient`,
qui est le point d'entrée de communication avec une application de test.
"""

import socket
import errno
import subprocess
import os
import time
from functools import wraps
from collections import defaultdict
import shlex
from scletest.aliases import HooqAliases
from scletest.models import Widget, WidgetsTree
from xml.dom import minidom

import logging

LOG = logging.getLogger('scletest.sclehooq')

class AckError(Exception):
    """
    Exception levée lors de recu d'acquitement négatif.
    """
    pass

class ScleHooqClient(object):
    """
    Client pour la connexion avec un socket contrôlé par scleHook.
    
    Cet objet est le point d'entrée pour l'envoi et la récupération des
    informations sur les objets de l'application testée.
    
    :param addr: adresse de l'application hôte. Défaut avec localhost.
    :param port: le port de communication scleHooq
    :param aliases: un objet HooqAliases pour gérer les alias. Peut être
                    un nom de fichier, qui génèrera alors une instance
                    de HooqAliases via :func:`HooqAliases.from_file`
    """
    
    DEFAUT_HOOQ_ADDR = 'localhost'
    DEFAUT_HOOQ_PORT = 9999
    
    ACQUIT_OK = "ACK"
    ACQUIT_ERROR = "ERROR"
    
    COMMANDE_NO_OP = '<noOp/>'

    COMMANDE_DUMP_WIDGETS = '<dumpWidgetsTree/>'
    COMMANDE_DUMP_PROPERTIES = '<dumpProperties target="{0}"/>'
    COMMANDE_DUMP_MODEL = '<dumpModel target="{0}"/>'

    COMMANDE_GET_WIDGET = '<getWidget target="{0}"/>'
    COMMANDE_CLICK_WIDGET = '<clickWidget target="{0}"/>'
    COMMANDE_DOUBLE_CLICK_WIDGET = '<doubleClickWidget target="{0}"/>'
    
    COMMANDE_GET_ITEM = ('<getItem view_target="{view_target}"'
                           ' item_path="{item_path}"'
                           ' row="{row}"'
                           ' column="{column}"/>')
    COMMANDE_MODEL_ITEM = ('<{action} view_target="{view_target}"'
                           ' item_path="{item_path}"'
                           ' row="{row}"'
                           ' column="{column}"/>')
    COMMANDE_SET_PROPERTY = ('<setProperty target="{target}"'
                            ' propType="{propType}"'
                            ' propValue="{propValue}"'
                            ' propName="{propName}"/>')
    COMMANDE_SHORTCUT = ('<shortcut target="{target}"'
                            ' keySequence="{keySequence}"/>')
    
    def __init__(self, addr=None, port=None, aliases=None, timeout_connection=10):
        self.addr = addr or self.DEFAUT_HOOQ_ADDR
        self.port = port or self.DEFAUT_HOOQ_PORT
        
        if aliases is None:
            aliases = HooqAliases()
        elif isinstance(aliases, basestring):
            aliases = HooqAliases.from_file(aliases)
        elif not isinstance(aliases, HooqAliases):
            raise TypeError("aliases must be None or str or an"
                             " instance of HooqAliases")
        
        self.aliases = aliases
        
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # tentative de connexion
        time_elapsed = 0.0
        while 1:
            try:
                self.socket.connect((self.addr, self.port))
            except socket.error, e:
                if e.errno == errno.ECONNREFUSED:
                    if time_elapsed >= timeout_connection:
                        raise
                    time.sleep(0.2)
                    time_elapsed += 0.2
                else:
                    raise
            else:
                break
                
        
        # teste la connexion
        self.no_op()
    
    def close(self):
        """
        Ferme le socket de connexion avec scleHook.
        
        L'objet devient inutilisable après appel de cette méthode.
        Cette méthode est appelée automatiquement sur destruction de l'objet.
        """
        if self.socket:
            self.socket.close()
    
    def __del__(self):
        self.close()
    
    def send_command(self, cmd, timeout=0.0, timeout_interval=0.1):
        """
        Envoi une commande au serveur scleHooq et retourne la réponse
        au format texte.
        """
        elapsed_time = 0.0
        while 1:
            try:
                return self._send_command(cmd)
            except AckError:
                if elapsed_time >= timeout:
                    raise
                time.sleep(timeout_interval)
                elapsed_time += timeout_interval
            else:
                break
    
    def _send_command(self, cmd):
        """
        Envoi une commande au serveur scleHooq et retourne la réponse
        au format texte.
        
        :param cmd: la commande à envoyer, sans le retour a la ligne final.
        :raises AckError: lors de réception d'erreur ACK
        """
        LOG.debug("send_command: %s", cmd)
        self.socket.sendall(cmd + "\n")
        
        buffer_ = ''
        lines = []
        done = False
        while not done:
            more = self.socket.recv(4096)
            if not more:
                raise Exception("Erreur de reception de la commande `%s`" % cmd)
            buffer_ += more
            while "\n" in buffer_:
                (line, buffer_) = buffer_.split("\n", 1)
                LOG.debug("reception: %s" % line)
                if line == self.ACQUIT_OK:
                    done = True
                    break
                elif line == self.ACQUIT_ERROR:
                    raise AckError("Erreur d'acquittement lors de la"
                                    " commande `%s`. Message:\n%s" % (
                                    (cmd, '\n'.join(lines))))
                else:
                    lines.append(line)
        return '\n'.join(lines)
    
    def no_op(self):
        """
        Envoie la commande NO_OP au serveur scleHooq.
        
        Basiquement utilisé pour tester la communication serveur.
        """
        self.send_command(self.COMMANDE_NO_OP)

    def shortcut(self, sequence):
        """
        Envoie une QKeySequence sur la fenêtre ayant le focus.
        Voir la documentation de QKeySequence::fromString pour
        savoir quoi passer pour l'argument `sequence`.
        """
        self.send_command(self.COMMANDE_SHORTCUT.format(target='',
                                             keySequence=sequence))

    def widgets_tree(self):
        """
        Renvoie une instance de :class:`scletest.models.WidgetsTree`
        demandée au serveur.
        """
        dump = self.send_command(self.COMMANDE_DUMP_WIDGETS)
        return WidgetsTree.parse_and_attach(self, dump)
    
    def widget(self, alias=None, path=None, timeout=10, timeout_interval=0.1):
        """
        Renvoie une instance de :class:`scletest.models.Widget`
        identifiée par un alias ou un chemin complet.
        
        :param alias: alias de chemin de widget défini dans le fichier
                      d'alias.
        :param path: le chemin complet vers un widget.
        """
        if not (alias or path):
            raise TypeError("alias or path must be defined")
        
        if alias:
            path = self.aliases[alias]
        
        dump = self.send_command(self.COMMANDE_GET_WIDGET.format(path),
                                 timeout=timeout,
                                 timeout_interval=timeout_interval)
        return Widget.parse_and_attach(self, dump)
    
    def dump_widgets_tree(self, stream, pretty=True):
        """
        Ecrit dans l'objet file-like un dump xml des widgets. Si stream
        est une chaine, un fichier est ouvert en écriture automatiquement.
        
        :param stream: objet file-like (disposant d'une methode write)
                       ou un chemin vers un fichier.
        :param pretty: booleen pour indiquer si le xml doit être
                       indenté pour plus de lisibilité
        """
        if isinstance(stream, basestring):
            stream = open(stream, 'w')
        xml = self.widgets_tree().render()
        if pretty:
            xml = minidom.parseString(xml).toprettyxml()
        stream.write(xml)
        

class ApplicationContext(object): # pylint: disable=R0903
    """
    Représente le contexte d'une application testée.
    
    L'instanciation de cette classe peut lancer l'exécutable à tester
    avec scleHooq (si appconfig.executable ne commence pas par 
    "socket://").
    
    Ensuite on tente de se connecter au serveur via une instance de
    :class:`ScleHooqClient` accessible par la variable membre **hooq**.
    
    A la destruction de cette instance, la méthode :meth:`terminate`
    est automatiquement appellée et ferme l'objet **hooq** ainsi que le
    processus testé s'il a été créé.
    """
    def __init__(self, appconfig):
        self._process, self.hooq = None, None
        
        if not appconfig.executable.startswith('socket://'):
            self._start_test_process(appconfig)
            addr = None # means localhost
        else:
            addr = appconfig.executable[9:]
        
        self.hooq = ScleHooqClient(addr=addr,
                                   port=appconfig.hooq_port,
                                   aliases=appconfig.aliases,
                                   timeout_connection=appconfig.timeout_connection)
    
    def _start_test_process(self, appconfig):
        """
        Demarre le process de l'appli à tester.
        """
        env = appconfig.env
        if env is None:
            env = os.environ
        
        # copy env
        env = dict(env.items())
        
        env['SCLEHOOQ_ACTIVATION'] = '1'
        hooq_port = appconfig.hooq_port
        if hooq_port:
            env['SCLEHOOQ_PORT'] = str(hooq_port)
        
        cmd = [appconfig.executable]
        cmd.extend(appconfig.args)
        
        stdout = appconfig.executable_stdout
        stderr = appconfig.executable_stderr
        
        if stderr:
            if stderr == stdout:
                stderr = subprocess.STDOUT
            else:
                stderr = open(stderr, 'a')
        if stdout:
            stdout = open(stdout, 'a')
        
        self._process = subprocess.Popen(cmd,
                                         cwd=appconfig.cwd,
                                         stdout=stdout,
                                         stderr=stderr,
                                         env=env)
    
    def _kill_process(self):
        if self._process:
            # attente de fermeture gentille
            max_wait, intervall = 10, 0.05
            while max_wait > 0 and self._process.poll() is None:
                time.sleep(intervall)
                max_wait -= intervall
            if self._process.returncode is None:
                # application bloquée ! pas le choix ...
                self._process.terminate()
            self._process = None
    
    def terminate(self):
        """
        Tente de tuer le process de test et ferme l'objet **hooq**.
        """
        if self.hooq:
            if self._process is not None:
                # mode attache, on doit gerer la fin du process
                # demande de fermeture, gentiment (qApp->quit()).
                self.hooq.socket.sendall('<qAppQuitGently/>')
            self.hooq.close()
            self.hooq = None
        self._kill_process()
    
    def __del__(self):
        self.terminate()

class ApplicationConfig(object): # pylint: disable=R0902
    """
    Cet objet permet de créer des :class:`ApplicationContext`.
    
    :param executable: chemin complet vers l'exécutable de test
    :param args: arguments de l'exécutable
    :param hooq_port: Spécifie un port pour la communication scleHooq
    :param cwd: Répertoire d'exécution de l'exécutable. Si None,
                l'exécutable sera lancé depuis son propre dossier
    :param env: dict représentant les variables d'environnement à passer
                lors de l'exécution de l'exécutable. Si None, os.environ
                est utilisé
    :param timeout_connection: temps d'attente maximum avant de déclarer
                              forfait pour la connexion scleHooq.
    """
    def __init__(self, executable,
                       args=(),
                       hooq_port=None,
                       cwd=None,
                       env=None,
                       timeout_connection=10,
                       aliases=None,
                       executable_stdout=None,
                       executable_stderr=None): # pylint: disable=R0913
        self.executable = executable
        self.args = args
        self.hooq_port = hooq_port
        self.cwd = cwd or os.path.dirname(executable) or os.getcwd()
        self.env = env
        self.timeout_connection = timeout_connection
        self.aliases = aliases
        self.executable_stdout = executable_stdout
        self.executable_stderr = executable_stderr
    
    @classmethod
    def from_conf(cls, conf, section, basedir=None):
        """
        Génère une instance de :class:`ApplicationConfig` à partir
        d'un fichier de configuration lu par ConfigParser.
        """
        executable = conf.get(section, 'executable')
        if not executable.startswith('socket://') and (
                        basedir and not os.path.isabs(executable)):
            executable = os.path.join(basedir, executable)
        
        kwargs = {}
        if conf.has_option(section, 'args'):
            kwargs['args'] = shlex.split(conf.get(section, 'args'))

        if conf.has_option(section, 'hooq_port'):
            kwargs['hooq_port'] = conf.getint(section, 'hooq_port')

        if conf.has_option(section, 'timeout_connection'):
            kwargs['timeout_connection'] = conf.getint(section,
                                             'timeout_connection')
        
        for optname in ('cwd', 'aliases', 'executable_stdout',
                         'executable_stderr'):
            if conf.has_option(section, optname):
                kwargs[optname] = conf.get(section, optname)
                if basedir and not os.path.isabs(kwargs[optname]):
                    kwargs[optname] = os.path.join(basedir, kwargs[optname])
        
        # devnull si NULL spécifié dans le fichier de conf
        for optname in ('executable_stdout', 'executable_stderr'):
            if conf.has_option(section, optname) and \
                            conf.get(section, optname) == 'NULL':
                kwargs[optname] = os.devnull
        
        return cls(executable, **kwargs) # pylint: disable=W0142

    def create_context(self):
        """
        Retourne une instance de :class:`ApplicationContext`.
        """
        return ApplicationContext(self)
    
    def with_hooq(self, meth):
        """
        Décorateur simple de fonction permettant de créer un contexte
        qui sera passé en argument et automatiquement détruit après
        exécution de cette fonction.
        """
        @wraps(meth)
        def wrapper():
            ctx = self.create_context()
            return meth(ctx.hooq)
        return wrapper

class MultiApplicationConfig(tuple):
    """
    Permet de manipuler plusieurs applications de test en même temps.
    """
    def __init__(self, appconfigs):
        tuple.__init__(appconfigs)
    
    def with_hooq(self, meth):
        """
        Décorateur simple de fonction permettant de créer les contextes
        des :class:`ApplicationConfig` stockées qui seront
        automatiquement détruits après exécution de la fonction.
        """
        @wraps(meth)
        def wrapper():
            ctxs = [ appconfig.create_context() for appconfig
                     in self]
            return meth(*[ctx.hooq for ctx in ctxs])
        return wrapper

class ApplicationRegistry(object):
    """
    Gère un ensemble de :class:`ApplicationConfig`. Une instance
    globale est utilisée dans :mod:`sclehooq.noseplugin` pour stocker
    les ApplicationConfig déclarées par le fichier de conf.
    """
    def __init__(self):
        self.confs = defaultdict(dict)
    
    def register_from_conf(self, conf, basedir):
        for section in conf.sections():
            if ':' in section:
                app, mode = section.split(':', 1)
            else:
                app, mode = section, 'default'
            appconf = ApplicationConfig.from_conf(conf, section, basedir)
            self.register_config(app, appconf, mode)
    
    def register_config(self, name, conf, mode='default'):
        self.confs[name][mode] = conf
    
    def config(self, name, mode='default'):
        return self.confs[name][mode]
    
    def multi_config(self, names, mode='default'):
        return MultiApplicationConfig(
                    [ self.config(name, mode) for name in names ])
