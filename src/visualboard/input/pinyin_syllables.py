"""《汉语拼音方案》无声调音节。

j / q / x / y 后面的 ü 写成键盘上的 u（ju、qu、xu、yu）。
n / l 后面的 ü 写成键盘上的 v（nv、lv、nve、lve）。
这是一张固定音节表，不是声母和韵母的笛卡尔积。
"""

from __future__ import annotations

_SYLLABLE_TEXT = """
a ai an ang ao
ba bai ban bang bao bei ben beng bi bian biao bie bin bing bo bu
pa pai pan pang pao pei pen peng pi pian piao pie pin ping po pu
ma mai man mang mao me mei men meng mi mian miao mie min ming mo mu
fa fan fang fei fen feng fo fou fu
da dai dan dang dao de dei den deng di dia dian diao die ding diu dong dou du duan dui dun duo
ta tai tan tang tao te teng ti tian tiao tie ting tong tou tu tuan tui tun tuo
na nai nan nang nao ne nei nen neng ni nian niang niao nie nin ning niu nong nou nu nuan nuo nv nve
la lai lan lang lao le lei leng li lia lian liang liao lie lin ling liu long lou lu luan lun luo lv lve
ga gai gan gang gao ge gei gen geng gong gou gu gua guai guan guang gui gun guo
ka kai kan kang kao ke kei ken keng kong kou ku kua kuai kuan kuang kui kun kuo
ha hai han hang hao he hei hen heng hong hou hu hua huai huan huang hui hun huo
ji jia jian jiang jiao jie jin jing jiong jiu ju juan jue jun
qi qia qian qiang qiao qie qin qing qiong qiu qu quan que qun
xi xia xian xiang xiao xie xin xing xiong xiu xu xuan xue xun
zha zhai zhan zhang zhao zhe zhei zhen zheng zhong zhou zhu zhua zhuai zhuan zhuang zhui zhun zhuo
cha chai chan chang chao che chen cheng chong chou chu chua chuai chuan chuang chui chun chuo
sha shai shan shang shao she shei shen sheng shou shu shua shuai shuan shuang shui shun shuo
ran rang rao re ren reng ri rong rou ru rua ruan rui run ruo
za zai zan zang zao ze zei zen zeng zong zou zu zuan zui zun zuo
ca cai can cang cao ce cen ceng cong cou cu cuan cui cun cuo
sa sai san sang sao se sen seng song sou su suan sui sun suo
ya yan yang yao ye yi yin ying yo yong you yu yuan yue yun
wa wai wan wang wei wen weng wo wu
e ei en eng er o ou
"""

SYLLABLES: frozenset[str] = frozenset(_SYLLABLE_TEXT.split())

# 只在测试里打开。默认的合法性判断不使用这两张表。
FUZZY_INITIALS: tuple[tuple[str, str], ...] = (
    ("z", "zh"),
    ("c", "ch"),
    ("s", "sh"),
    ("n", "l"),
)
FUZZY_FINALS: tuple[tuple[str, str], ...] = (
    ("an", "ang"),
    ("en", "eng"),
    ("in", "ing"),
)

_PREFIXES: frozenset[str] = frozenset(
    syllable[:end]
    for syllable in SYLLABLES
    for end in range(1, len(syllable) + 1)
)


def is_legal(
    text: str,
    *,
    fuzzy_initials: bool = False,
    fuzzy_finals: bool = False,
) -> bool:
    """S 合法：若干完整音节之后，可以再接一个音节前缀（也可以接完）。"""
    if fuzzy_initials or fuzzy_finals:
        return any(
            _is_legal_strict(variant)
            for variant in _fuzzy_variants(text, fuzzy_initials, fuzzy_finals)
        )
    return _is_legal_strict(text)


def _is_legal_strict(text: str) -> bool:
    if text == "":
        return True
    size = len(text)
    reached = [False] * (size + 1)
    reached[0] = True
    for start in range(size):
        if not reached[start]:
            continue
        rest = text[start:]
        if rest in _PREFIXES:
            return True
        for syllable in SYLLABLES:
            if rest.startswith(syllable):
                reached[start + len(syllable)] = True
    return False


def _fuzzy_variants(text: str, initials: bool, finals: bool) -> set[str]:
    pairs: list[tuple[str, str]] = []
    if initials:
        for left, right in FUZZY_INITIALS:
            pairs.append((left, right))
            pairs.append((right, left))
    if finals:
        for left, right in FUZZY_FINALS:
            pairs.append((left, right))
            pairs.append((right, left))
    seen = {text}
    queue = [text]
    while queue and len(seen) < 64:
        current = queue.pop()
        for source, target in pairs:
            start = 0
            while True:
                index = current.find(source, start)
                if index < 0:
                    break
                if _inside_longer_initial(current, index, source):
                    start = index + 1
                    continue
                variant = current[:index] + target + current[index + len(source) :]
                if variant not in seen:
                    seen.add(variant)
                    queue.append(variant)
                start = index + 1
    return seen


def _inside_longer_initial(text: str, index: int, source: str) -> bool:
    """不要把 zh 里的 z 再换成 zh。"""
    if source not in ("z", "c", "s"):
        return False
    return text[index : index + 2] == source + "h"
