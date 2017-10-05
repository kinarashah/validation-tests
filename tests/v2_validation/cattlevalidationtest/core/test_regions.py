from common_fixtures import *  # NOQA


REGION_NAME = 'region1'
SERVICE_ACCOUNT_NAME = 'region1'


@pytest.fixture
def region_url(admin_user_client):
    default_url = 'http://localhost:8080'
    return os.environ.get('CATTLE_TEST_URL', default_url)


@pytest.fixture
def p1(admin_user_client):
    ps = admin_user_client.list_project(name='Default')
    assert len(ps) == 1
    return ps[0]


@pytest.fixture
def p2(admin_user_client):
    ps = admin_user_client.list_project(name='foo')
    assert len(ps) == 1
    return ps[0]


@pytest.fixture
def p3(admin_user_client):
    ps = admin_user_client.list_project(name='bar')
    assert len(ps) == 1
    return ps[0]


def test_region_links(admin_user_client, super_client, p1, p2, region_url):
    cleanup_region_data(super_client, p1, p2)
    client1 = client_for_project(p1)
    assert len(client1.list_host()) > 0
    client2 = client_for_project(p2)
    assert len(client2.list_host()) > 0

    sa = admin_user_client.create_account(name=SERVICE_ACCOUNT_NAME,
                                          kind="service")
    assert sa.name == SERVICE_ACCOUNT_NAME
    assert sa.kind == "service"

    # service account will be used for cross-environment agent creation
    sa_key = admin_user_client.create_api_key(accountId=sa.id)
    assert sa_key.state == 'registering'
    assert sa_key.accountId == sa.id

    region = admin_user_client.create_region(name=REGION_NAME,
                                             publicValue=sa_key.publicValue,
                                             secretValue=sa_key.secretValue,
                                             url=region_url,
                                             local=True)
    assert region.name == REGION_NAME
    assert region.url == region_url
    assert region.local is True
    assert region.publicValue == sa_key.publicValue
    assert region.secretValue == sa_key.secretValue

    s1, stack1 = create_env_and_svc(client1)
    s2, stack2 = create_env_and_svc(client2)
    link_svc = "%s/%s/%s/%s" % (REGION_NAME, p2.name, stack2.name, s2.name)
    link_alias = "mylink"
    link = {"service": link_svc, "name": link_alias}
    s1. \
        setservicelinks(serviceLinks=[link])

    # "foreign" agent in env2
    wait_for(lambda: get_agent(super_client, p1.id) is not None)
    agent1 = get_agent(super_client, p1.id)
    assert agent1.agentResourcesAccountId == p1.id

    # "foreign" agent in env1
    wait_for(lambda: get_agent(super_client, p2.id) is not None)
    agent2 = get_agent(super_client, p2.id)
    assert agent2.agentResourcesAccountId == p2.id

    # reset service links and the agents should be gone
    s1. \
        setservicelinks(serviceLinks=[])
    wait_for(lambda: get_agent(super_client, p1.id) is None)
    wait_for(lambda: get_agent(super_client, p2.id) is None)

    delete_all(client1, [stack1])
    delete_all(client2, [stack2])
    cleanup_region_data(super_client, p1, p2)


def test_region_lb(admin_user_client, super_client, p1, p2, region_url):
    cleanup_region_data(super_client, p1, p2)
    client1 = client_for_project(p1)
    assert len(client1.list_host()) > 0
    client2 = client_for_project(p2)
    assert len(client2.list_host()) > 0

    sa = admin_user_client.create_account(name=SERVICE_ACCOUNT_NAME,
                                          kind="service")
    assert sa.name == SERVICE_ACCOUNT_NAME
    assert sa.kind == "service"

    # service account will be used for cross-environment agent creation
    sa_key = admin_user_client.create_api_key(accountId=sa.id)
    assert sa_key.state == 'registering'
    assert sa_key.accountId == sa.id

    region = admin_user_client.create_region(name=REGION_NAME,
                                             publicValue=sa_key.publicValue,
                                             secretValue=sa_key.secretValue,
                                             url=region_url,
                                             local=True)
    assert region.name == REGION_NAME
    assert region.url == region_url
    assert region.local is True
    assert region.publicValue == sa_key.publicValue
    assert region.secretValue == sa_key.secretValue

    # create LB and point port rule to another environment
    launch_config = {"imageUuid": "docker:ubuntu:latest"}
    stack = create_env(client1)
    port_rule = {"protocol": "tcp", "selector": "foo=bar",
                 "environment": p2.name,
                 "region": REGION_NAME,
                 "sourcePort": 944}
    port_rules = [port_rule]
    lb_config = {"portRules": port_rules}

    lb = client1. \
        create_loadBalancerService(name=random_str(),
                                   stackId=stack.id,
                                   launchConfig=launch_config,
                                   lbConfig=lb_config)

    lb = client1.wait_success(lb)

    # "foreign" agent in env2
    wait_for(lambda: get_agent(super_client, p1.id) is not None)
    agent1 = get_agent(super_client, p1.id)
    assert agent1.agentResourcesAccountId == p1.id

    # "foreign" agent in env1
    wait_for(lambda: get_agent(super_client, p2.id) is not None)
    agent2 = get_agent(super_client, p2.id)
    assert agent2.agentResourcesAccountId == p2.id

    # set port rules to none on lb service, validate the agents are gone
    lb_config = {"portRules": []}
    lb = client1.update(lb, lbConfig=lb_config)
    lb = client1.wait_success(lb)
    wait_for(lambda: get_agent(super_client, p1.id) is None)
    wait_for(lambda: get_agent(super_client, p2.id) is None)

    # set port rules to original, validate agents are back
    lb_config = {"portRules": port_rules}
    lb = client1.update(lb, lbConfig=lb_config)
    lb = client1.wait_success(lb)
    wait_for(lambda: get_agent(super_client, p1.id) is not None)
    wait_for(lambda: get_agent(super_client, p2.id) is not None)

    # remove lb service
    lb.remove()
    wait_for(lambda: get_agent(super_client, p1.id) is None)
    wait_for(lambda: get_agent(super_client, p2.id) is None)

    delete_all(client1, [stack])
    cleanup_region_data(super_client, p1, p2)


def test_regions_setup(admin_user_client, super_client, p1, p2, p3, region_url):
    cleanup_region_data(super_client, p1, p2)
    client1 = client_for_project(p1)
    assert len(client1.list_host()) > 0
    client2 = client_for_project(p2)
    assert len(client2.list_host()) > 0
    client3 = client_for_project(p3)
    assert len(client3.list_host()) > 0

    sa = admin_user_client.create_account(name=SERVICE_ACCOUNT_NAME,
                                          kind="service")
    assert sa.name == SERVICE_ACCOUNT_NAME
    assert sa.kind == "service"

    # service account will be used for cross-environment agent creation
    sa_key = admin_user_client.create_api_key(accountId=sa.id)
    assert sa_key.state == 'registering'
    assert sa_key.accountId == sa.id

    region = admin_user_client.create_region(name=REGION_NAME,
                                             publicValue=sa_key.publicValue,
                                             secretValue=sa_key.secretValue,
                                             url=region_url,
                                             local=True)
    assert region.name == REGION_NAME
    assert region.url == region_url
    assert region.local is True
    assert region.publicValue == sa_key.publicValue
    assert region.secretValue == sa_key.secretValue

    # link Default and foo using service links
    s1, stack1 = create_env_and_svc(client1)
    s2, stack2 = create_env_and_svc(client2)
    link_svc1 = "%s/%s/%s/%s" % (REGION_NAME, p2.name, stack2.name, s2.name)
    link_alias1 = "mylink"
    link1 = {"service": link_svc1, "name": link_alias1}
    s1. \
        setservicelinks(serviceLinks=[link1])

    # "foreign" agent in env2
    wait_for(lambda: get_agent(super_client, p1.id) is not None)
    agent1 = get_agent(super_client, p1.id)
    assert agent1.agentResourcesAccountId == p1.id

    # "foreign" agent in env1
    wait_for(lambda: get_agent(super_client, p2.id) is not None)
    agent2 = get_agent(super_client, p2.id)
    assert agent2.agentResourcesAccountId == p2.id

    # link Default and bar using selector
    launch_config = {"imageUuid": "docker:kinarashah/lb:linux5"}
    stack = create_env(client1)
    port_rule = {"protocol": "tcp", "selector": "foo=bar",
                 "environment": p3.name,
                 "region": REGION_NAME,
                 "sourcePort": 944,
                 "weight": 100}
    port_rules = [port_rule]
    lb_config = {"portRules": port_rules}

    lb = client1. \
        create_loadBalancerService(name=random_str(),
                                   stackId=stack.id,
                                   launchConfig=launch_config,
                                   lbConfig=lb_config)

    client1.wait_success(lb)
    wait_for(lambda: get_agent(super_client, p3.id) is not None)
    agent1 = get_agent(super_client, p3.id)
    assert agent1.agentResourcesAccountId == p3.id


def get_agent(super_client, resourceAccountId):
    agents = super_client.list_agent()
    for agent in agents:
        if agent.agentResourcesAccountId == resourceAccountId:
            return agent
    return None

def create_env_and_svc(client):
    launch_config = {"imageUuid": "docker:ubuntu:latest"}
    random_name = random_str()
    service_name = random_name.replace("-", "")
    env = create_env(client)
    s = client.create_service(name=service_name,
                              stackId=env.id,
                              launchConfig=launch_config)
    return s, env


def create_env(client):
    random_name = random_str()
    env_name = random_name.replace("-", "")
    env = client.create_stack(name=env_name)
    env = client.wait_success(env)
    assert env.state == "active"
    return env


def cleanup_region_data(super_client, p1, p2):
    acs = super_client.list_account(name=SERVICE_ACCOUNT_NAME)
    if len(acs) > 0:
        sa = acs[0]
        if sa.state == 'active':
            sa.deactivate()
        super_client.wait_success(sa)
        super_client.delete(sa)
    for r in super_client.list_region():
        super_client.delete(r)
        super_client.wait_success(r)
