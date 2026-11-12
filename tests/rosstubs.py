"""Minimal stand-ins for ROS, cv_bridge, tf2_ros and the RKNN runtime, so the drone code can be
imported and its logic tested on any computer. They record what the code publishes; they do not
simulate ROS. Nothing here is used on the drone."""
import importlib.util
import os
import sys
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLISHED = []      # (topic, data) for every publish
PARAMS = {}         # private params, keys like '~input_topic'
TF = {}             # (target, source) -> transform object for tf2_ros.Buffer.lookup_transform


def _mod(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


class _Msg:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Publisher:
    def __init__(self, topic, *_a, **_k):
        self.topic = topic

    def publish(self, msg):
        PUBLISHED.append((self.topic, getattr(msg, 'data', msg)))

    def get_num_connections(self):
        return 0


class _Duration:
    def __init__(self, s=0):
        self.s = s


class _Time:
    def __init__(self, s=0):
        self.s = s

    @staticmethod
    def from_sec(s):
        return _Time(s)

    def to_sec(self):
        return self.s


class _LookupException(Exception):
    pass


class _ConnectivityException(Exception):
    pass


class _ExtrapolationException(Exception):
    pass


class _Buffer:
    def __init__(self, *_a):
        pass

    def lookup_transform(self, target, source, _t, _timeout):
        if (target, source) not in TF:
            raise _LookupException('no tf %s <- %s' % (target, source))
        return TF[(target, source)]


class _CvBridge:
    def imgmsg_to_cv2(self, msg, desired_encoding=None):
        return msg.img

    def cv2_to_imgmsg(self, img, encoding=None):
        return _Msg(img=img, header=None)


class _RKNNLite:
    NPU_CORE_AUTO = 0
    OUTPUT = None          # what inference() returns; set by the test

    def load_rknn(self, _path):
        return 0

    def init_runtime(self, core_mask=None):
        return 0

    def inference(self, inputs):
        _RKNNLite.LAST_INPUT = inputs[0]
        return _RKNNLite.OUTPUT

    def release(self):
        pass


def _log(*_a, **_k):
    pass


def install():
    """Put the stand-ins into sys.modules (idempotent)."""
    if getattr(sys.modules.get('rospy'), '_brics_stub', False):
        return
    _mod('rospy', _brics_stub=True, Publisher=_Publisher, Subscriber=lambda *a, **k: None, Timer=lambda *a, **k: None,
         Duration=_Duration, Time=_Time, init_node=_log, spin=_log, on_shutdown=_log,
         get_param=lambda n, d=None: PARAMS.get(n, d), has_param=lambda n: n in PARAMS,
         loginfo=_log, logwarn=_log, logerr=_log, logwarn_throttle=_log, logerr_throttle=_log,
         wait_for_message=_log, ROSInterruptException=type('ROSInterruptException', (Exception,), {}),
         ROSException=type('ROSException', (Exception,), {}))
    rg = _mod('rosgraph')
    rg.roslogging = _mod('rosgraph.roslogging', configure_logging=_log)
    for pkg, names in (('std_msgs', ('String', 'Empty')), ('sensor_msgs', ('Image', 'CameraInfo', 'Range')),
                       ('geometry_msgs', ('PoseStamped',))):
        p = _mod(pkg)
        p.msg = _mod(pkg + '.msg', **{n: type(n, (_Msg,), {}) for n in names})
    _mod('cv_bridge', CvBridge=_CvBridge)
    _mod('tf2_ros', Buffer=_Buffer, TransformListener=lambda *a, **k: None, LookupException=_LookupException,
         ConnectivityException=_ConnectivityException, ExtrapolationException=_ExtrapolationException)
    _mod('message_filters', Subscriber=lambda *a, **k: None, ApproximateTimeSynchronizer=lambda *a, **k: None)
    rk = _mod('rknnlite')
    rk.api = _mod('rknnlite.api', RKNNLite=_RKNNLite)
    rk.api.rknn_platform_utils = _mod('rknnlite.api.rknn_platform_utils')


def load(relpath, name):
    """Import a repository file (e.g. 'drone/fire_geoloc.py') as a module, with the stand-ins installed."""
    install()
    path = os.path.join(REPO, relpath)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def transform(x, y, z, qx, qy, qz, qw):
    """A geometry_msgs/TransformStamped-like object for TF."""
    return _Msg(transform=_Msg(translation=_Msg(x=x, y=y, z=z), rotation=_Msg(x=qx, y=qy, z=qz, w=qw)))


Msg = _Msg
RKNNLite = _RKNNLite
