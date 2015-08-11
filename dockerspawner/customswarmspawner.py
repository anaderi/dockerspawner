from tornado import gen
from dockerspawner import CustomDockerSpawner

# urllib3 complains that we're making unverified HTTPS connections to swarm,
# but this is ok because we're connecting to swarm via 127.0.0.1. I don't
# actually want swarm listening on a public port, so I don't want to connect
# to swarm via the host's FQDN, which means we can't do fully verified HTTPS
# connections. To prevent the warning from appearing over and over and over
# again, I'm just disabling it for now.
import requests
requests.packages.urllib3.disable_warnings()


class CustomSwarmSpawner(CustomDockerSpawner):

    container_ip = '0.0.0.0'
    start_timeout = 180

    def __init__(self, **kwargs):
        super(CustomSwarmSpawner, self).__init__(**kwargs)

    @gen.coroutine
    def lookup_node_name(self):
        """Find the name of the swarm node that the container is running on."""
        containers = yield self.docker('containers', all=True)
        for container in containers:
            if container['Id'] == self.container_id:
                name, = container['Names']
                node, container_name = name.lstrip("/").split("/")
                raise gen.Return(node)

    @gen.coroutine
    def start(self, image=None, extra_create_kwargs=None):
        # look up mapping of node names to ip addresses
        info = yield self.docker('info')
        name_host = [(e[0], e[1].split(':')[0]) for e in info['DriverStatus'][4:] if len(e) == 2 and e[1].endswith('2375')]
        self.node_info = dict(name_host)
        self.log.debug("Swarm nodes are: {}".format(self.node_info))

        # start the container
        if extra_create_kwargs is None:
            extra_create_kwargs = {}
        if 'mem_limit' not in extra_create_kwargs:
            extra_create_kwargs['mem_limit'] = '1g'
        self.log.debug("Spawning container: {}, args: {}".format(image, extra_create_kwargs))

        yield super(CustomSwarmSpawner, self).start(
            image=image
        )

        # figure out what the node is and then get its ip
        name = yield self.lookup_node_name()
        self.user.server.ip = self.node_info[name]
        self.log.info("{} was started on {} ({}:{})".format(
            self.container_name, name, self.user.server.ip, self.user.server.port))

        self.log.info(self.env)
