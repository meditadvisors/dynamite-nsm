import os
import sys
import time
import signal
import shutil
import tarfile
import subprocess
from multiprocessing import Process

from installer import const
from installer import utilities

CONFIGURATION_DIRECTORY = '/etc/dynamite/elasticsearch/'
INSTALL_DIRECTORY = '/opt/dynamite/elasticsearch/'
LOG_DIRECTORY = '/var/log/dynamite/elasticsearch/'


class ElasticConfigurator:

    def __init__(self, configuration_directory):
        self.configuration_directory = configuration_directory
        self.es_config_options = self._parse_elasticyaml()
        self.jvm_config_options = self._parse_jvm_options()
        self.java_home = None
        self.es_home = None
        self.es_path_conf = None
        self._parse_environment_file()

    def _parse_elasticyaml(self):
        es_config_options = {}
        for line in open(os.path.join(self.configuration_directory, 'elasticsearch.yml')).readlines():
            if not line.startswith('#'):
                k, v = line.strip().split(':')
                es_config_options[k] = str(v).strip()
        return es_config_options

    def _parse_jvm_options(self):
        jvm_options = {}
        for line in open(os.path.join(self.configuration_directory, 'jvm.options')).readlines():
            if not line.startswith('#') and '-Xms' in line:
                jvm_options['initial_memory'] = line.replace('-Xms', '').strip()
            elif not line.startswith('#') and '-Xmx' in line:
                jvm_options['maximum_memory'] = line.replace('-Xmx', '').strip()
        return jvm_options

    def _parse_environment_file(self):
        for line in open('/etc/environment').readlines():
            if line.startswith('JAVA_HOME'):
                self.java_home = line.split('=')[1].strip()
            elif line.startswith('ES_PATH_CONF'):
                self.es_path_conf = line.split('=')[1].strip()
            elif line.startswith('ES_HOME'):
                self.es_home = line.split('=')[1].strip()

    def _overwrite_jvm_options(self):
        new_output = ''
        for line in open(os.path.join(self.configuration_directory, 'jvm.options')).readlines():
            if not line.startswith('#') and '-Xms' in line:
                new_output += '-Xms' + self.jvm_config_options['initial_memory']
            elif not line.startswith('#') and '-Xmx' in line:
                new_output += '-Xmx' + self.jvm_config_options['maximum_memory']
            else:
                new_output += line
            new_output += '\n'
        open(os.path.join(self.configuration_directory, 'jvm.options'), 'w').write(new_output)

    def get_cluster_name(self):
        return self.es_config_options.get('cluster.name')

    def get_network_host(self):
        return self.es_config_options.get('network.host')

    def get_network_port(self):
        return self.es_config_options.get('http.port')

    def get_data_path(self):
        return self.es_config_options.get('path.data')

    def get_log_path(self):
        return self.es_config_options.get('path.logs')

    def get_jvm_initial_memory(self):
        return self.jvm_config_options.get('initial_memory')

    def get_jvm_maximum_memory(self):
        return self.jvm_config_options.get('maximum_memory')

    def set_cluster_name(self, name):
        self.es_config_options['cluster.name'] = name

    def set_network_host(self, host):
        self.es_config_options['network.host'] = host

    def set_network_port(self, port):
        self.es_config_options['http.port'] = port

    def set_node_name(self, name):
        self.es_config_options['node.name'] = name

    def set_data_path(self, path):
        self.es_config_options['path.data'] = path

    def set_log_path(self, path):
        self.es_config_options['path.logs'] = path

    def set_discovery_seed_host(self, host_list):
        self.es_config_options['discovery.seed_hosts'] = host_list

    def set_jvm_initial_memory(self, gigs):
        self.jvm_config_options['initial_memory'] = str(int(gigs)) + 'g'

    def set_jvm_maximum_memory(self, gigs):
        self.jvm_config_options['maximum_memory'] = str(int(gigs)) + 'g'

    def write_configs(self):
        timestamp = int(time.time())
        backup_configurations = os.path.join(self.configuration_directory, 'config_backups/')
        es_config_backup = os.path.join(backup_configurations, 'elasticsearch.yml.backup.{}'.format(timestamp))
        java_config_backup = os.path.join(backup_configurations, 'java.options.backup.{}'.format(
            timestamp
        ))
        subprocess.call('mkdir -p {}'.format(backup_configurations), shell=True)
        shutil.move(os.path.join(self.configuration_directory, 'elasticsearch.yml'), es_config_backup)
        shutil.copy(os.path.join(self.configuration_directory, 'jvm.options'), java_config_backup)
        with open(os.path.join(self.configuration_directory, 'elasticsearch.yml'), 'a') as elastic_search_config_obj:
            for k, v in self.es_config_options.items():
                elastic_search_config_obj.write('{}: {}\n'.format(k, v))
        self._overwrite_jvm_options()


class ElasticInstaller:

    def __init__(self,
                 configuration_directory=CONFIGURATION_DIRECTORY,
                 install_directory=INSTALL_DIRECTORY,
                 log_directory=LOG_DIRECTORY):

        self.configuration_directory = configuration_directory
        self.install_directory = install_directory
        self.log_directory = log_directory

    def download_elasticsearch(self, stdout=False):
        for url in open(const.ELASTICSEARCH_MIRRORS, 'r').readlines():
            if utilities.download_file(url, const.ELASTICSEARCH_ARCHIVE_NAME, stdout):
                break

    def extract_elasticsearch(self, stdout=False):
        if stdout:
            sys.stdout.write('[+] Extracting: {} \n'.format(const.ELASTICSEARCH_ARCHIVE_NAME))
        try:
            tf = tarfile.open(os.path.join(const.INSTALL_CACHE, const.ELASTICSEARCH_ARCHIVE_NAME))
            tf.extractall(path=const.INSTALL_CACHE)
            sys.stdout.write('[+] Complete!\n')
            sys.stdout.flush()
        except IOError as e:
            sys.stderr.write('[-] An error occurred while attempting to extract file. [{}]\n'.format(e))

    def setup_elasticsearch(self, stdout=False):
        if stdout:
            sys.stdout.write('[+] Creating dynamite install/configuration/logging directories.\n')
        subprocess.call('mkdir -p {}'.format(self.install_directory), shell=True)
        subprocess.call('mkdir -p {}'.format(self.configuration_directory), shell=True)
        subprocess.call('mkdir -p {}'.format(self.log_directory), shell=True)
        subprocess.call('mkdir -p {}'.format(os.path.join(self.install_directory, 'data')), shell=True)
        subprocess.call('mkdir -p {}'.format('/var/run/dynamite/elasticsearch/'), shell=True)
        config_paths = [
            'config/elasticsearch.yml',
            'config/jvm.options',
            'config/log4j2.properties'
        ]
        install_paths = [
            'bin/',
            'lib/',
            'logs/',
            'modules/',
            'plugins/'
        ]
        for path in config_paths:
            try:
                shutil.move(os.path.join(const.INSTALL_CACHE, 'elasticsearch-7.1.1/{}'.format(path)),
                            self.configuration_directory)

            except shutil.Error as e:
                sys.stderr.write('[-] {} already exists at this path. [{}]\n'.format(path, e))
        for path in install_paths:
            try:
                shutil.move(os.path.join(const.INSTALL_CACHE, 'elasticsearch-7.1.1/{}'.format(path)),
                            self.install_directory)
            except shutil.Error as e:
                sys.stderr.write('[-] {} already exists at this path. [{}]\n'.format(path, e))
        if 'ES_PATH_CONF' not in open('/etc/environment').read():
            if stdout:
                sys.stdout.write('[+] Updating ElasticSearch default configuration path [{}]\n'.format(
                    self.configuration_directory))
            subprocess.call('echo ES_PATH_CONF="{}" >> /etc/environment'.format(self.configuration_directory),
                            shell=True)
        if 'ES_HOME' not in open('/etc/environment').read():
            if stdout:
                sys.stdout.write('[+] Updating ElasticSearch default home path [{}]\n'.format(
                    self.configuration_directory))
            subprocess.call('echo ES_HOME="{}" >> /etc/environment'.format(self.install_directory),
                            shell=True)
        sys.stdout.write('[+] Overwriting default configuration.\n')
        shutil.copy(os.path.join(const.DEFAULT_CONFIGS, 'elasticsearch', 'elasticsearch.yml'),
                    self.configuration_directory)
        utilities.set_ownership_of_file('/etc/dynamite/')
        utilities.set_ownership_of_file('/opt/dynamite/')
        utilities.set_ownership_of_file('/var/log/dynamite')
        utilities.set_ownership_of_file('/var/run/dynamite')
        es_config = ElasticConfigurator(configuration_directory=self.configuration_directory)
        sys.stdout.write('[+] Setting up JVM default heap settings [4GB]\n')
        es_config.set_jvm_initial_memory(4)
        es_config.set_jvm_maximum_memory(4)
        es_config.write_configs()
        sys.stdout.write('[+] Setting up Max File Handles [65535] VM Max Map Count [262144] \n')
        utilities.update_user_file_handle_limits()
        utilities.update_sysctl()


class ElasticProcess:

    def __init__(self, configuration_directory=CONFIGURATION_DIRECTORY):
        self.configuration_directory = configuration_directory
        self.config = ElasticConfigurator(self.configuration_directory)
        try:
            self.pid = int(open('/var/run/dynamite/elasticsearch/elasticsearch.pid').read())
        except IOError:
            self.pid = -1

    def start(self, stdout=False):
        def start_shell_out():
            subprocess.call('runuser -l dynamite -c "export JAVA_HOME={} && export ES_PATH_CONF={} '
                            '&& export ES_HOME={} && {}/bin/elasticsearch '
                            '-p /var/run/dynamite/elasticsearch/elasticsearch.pid --quiet &"'.format(self.config.java_home,
                                                                                                   self.config.es_path_conf,
                                                                                                   self.config.es_home,
                                                                                                   self.config.es_home),
                            shell=True)
        Process(target=start_shell_out).start()
        retry = 0
        self.pid = -1
        time.sleep(5)
        while retry < 6:
            start_message = '[+] [Attempt: {}] Starting ElasticSearch on PID [{}]\n'.format(retry + 1, self.pid)
            try:
                with open('/var/run/dynamite/elasticsearch/elasticsearch.pid') as f:
                    self.pid = int(f.read())
                start_message = '[+] [Attempt: {}] Starting ElasticSearch on PID [{}]\n'.format(retry + 1, self.pid)
                if stdout:
                    sys.stdout.write(start_message)
                if not utilities.check_pid(self.pid):
                    retry += 1
                    time.sleep(1)
                else:
                    return True
            except IOError:
                sys.stdout.write(start_message)
                retry += 1
                time.sleep(1)
        return False

    def stop(self, stdout=False):
        alive = True
        while alive:
            try:
                if stdout:
                    sys.stdout.write('[+] Attempting to stop ElasticSearch [{}]\n'.format(self.pid))
                os.kill(self.pid, signal.SIGTERM)
                time.sleep(1)
                alive = utilities.check_pid(self.pid)
            except Exception as e:
                sys.stderr.write('[-] An error occurred while attempting to stop ElasticSearch: {}\n'.format(e))
                return False
        return True

    def status(self):
        log_path = os.path.join(self.config.get_log_path(), self.config.get_cluster_name() + '.log')
        if os.path.exists(log_path):
            log_preview = utilities.tail_file(log_path, n=5)
        else:
            log_preview = None
        return {
            'PID': self.pid,
            'RUNNING': utilities.check_pid(self.pid),
            'JAVA_HEAP_INIT': self.config.get_jvm_initial_memory(),
            'JAVA_HEAP_MAX': self.config.get_jvm_maximum_memory(),
            'JAVA_HOME': self.config.java_home,
            'ES_HOME': self.config.es_home,
            'ES_PATH_CONF': self.config.es_path_conf,
            'ES_CONFIG_OPTIONS': self.config.es_config_options,
            'LOGS': log_preview
        }
