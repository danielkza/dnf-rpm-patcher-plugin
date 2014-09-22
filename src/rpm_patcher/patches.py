import fnmatch

from collections import namedtuple

from .util import is_str


class PatchSet(list):
    @classmethod
    def from_list(cls, list_):
        return PatchSet(Patch.from_dict(p) for p in list_)


class PatchSetDict(dict):
    @classmethod
    def from_dict(cls, dict_):
        return PatchSetDict({k: PatchSet.from_list(v)
                             for (k, v) in dict_.items()})

    def filter(self, exps, invert=False):
        keys = self.keys()

        for exp in exps:
            keys = fnmatch.filter(keys, exp)

        keys = set(keys)

        return PatchSetDict((k, v) for k, v in self if k in keys != invert)


class Patch(namedtuple('Patch', 'file options after_patch after_line')):


    @classmethod
    def _spec_find_patches(cls, lines):
        patch_re = re.compile(r'^Patch(\d+)', re.IGNORECASE)
        patch_apply_re = re.compile(r'^\s*%patch(\d+)', re.IGNORECASE)

        last_num = 0
        last_line_num = None
        last_apply_line_num = None

        for line_num, line in enumerate(lines):
            match = patch_re.match(line)
            if not match:
                continue

            patch_num = int(match.group(1))
            if patch_num > last_num:
                last_num = patch_num
                last_line_num = line_num

        for line_num, line in enumerate(lines[last_line_num + 1:],
                                        last_line_num + 1):
            match = patch_apply_re.match(line)
            if match:
                last_apply_line_num = line_num

        return last_num, last_line_num, last_apply_line_num

    def insert_patches(self, spec_file):
        with open(spec_file) as f:
            contents = f.readlines()

        last_num, last_line_num, last_apply_line_num = \
            self._find_last_patch(contents)

        patch_lines = []
        patch_apply_lines = []

        last_num = int(round(last_num, -2)) + 100

        for patch in self.patches:
            last_num += 1

            patch_id = 'Patch' + str(last_num)
            patch_line = '{0}: {1}\n'.format(patch_id, patch.file)
            patch_apply_line = '%patch{0} {1}\n'.format(last_num,
                                                        patch.options)

            self.logger.info(
                "Adding {0} as {1} with options '{2}'".format(
                    patch.file, patch_id, patch.options))

            patch_lines.append(patch_line)
            patch_apply_lines.append(patch_apply_line)

        new_contents = (
            contents[0:last_line_num + 1] +
            [''] + patch_lines + [''] +
            contents[last_line_num + 1:last_apply_line_num + 1] +
            [''] + patch_apply_lines + [''] +
            contents[last_apply_line_num + 1:])

        with open(spec_file, 'w') as f:
            f.writelines(new_contents)

    @classmethod
    def from_dict(cls, dict_):
        patch = dict_['patch']
        options = dict_.get('options', None)

        if options is None or is_str(options):
            pass
        elif all(is_str(e) for e in options):
            options = ' '.join(options)
        else:
            raise ValueError

        def list_val(val):
            if isinstance(val, list):
                return val
            elif hasattr(val, '__next__'):
                return list(val)
            elif not is_str(val):
                raise ValueError

            return [val]

        constraints = {}

        for key in ('after_patch', 'before_patch', 'after_line', 'before_line'):
            constraints[key] = list_val(dict_.get(key, []))

        return cls(file=patch, options=options, **constraints)
