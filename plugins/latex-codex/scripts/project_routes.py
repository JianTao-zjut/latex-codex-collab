"""Scope editor URLs to an explicit project, without touching document JSON."""
from copy import deepcopy
import re


ROUTES = ('vendor', 'state', 'save', 'compile', 'open', 'reload', 'project',
          'project-review', 'preferences', 'chat', 'collaboration', 'files',
          'source', 'download', 'pdf', 'outline', 'synctex', 'proofread',
          'history', 'markdown-resource', 'translation', 'join')
URL_LITERAL = re.compile(r'''(?<=["'`])/(?:''' + '|'.join(ROUTES) + r''')(?=[/"'`?#])''')


def scope_text(body, prefix):
    if prefix == '/':
        return body
    text = body.decode('utf-8')
    parts = re.split(r'''(<script\b[^>]*\btype=["']application/json["'][^>]*>.*?</script>)''', text, flags=re.S)
    text = ''.join(part if index % 2 else URL_LITERAL.sub(lambda match: prefix + match.group()[1:], part)
                   for index, part in enumerate(parts))
    # The invitation page's only root navigation is its successful login.
    text = text.replace("location.replace('/')", "location.replace('" + prefix + "')")
    return text.encode('utf-8')


def scope_response(data, prefix):
    if prefix == '/' or not isinstance(data, dict):
        return data
    result = dict(data)
    for key in ('pdf_url', 'before', 'after'):
        value = result.get(key)
        if isinstance(value, str) and value.startswith(('/history/pdf/', '/proofread/pdf')):
            result[key] = prefix + value[1:]
    if result.get('images') is True and isinstance(result.get('changes'), list):
        result['changes'] = deepcopy(result['changes'])
        for change in result['changes']:
            for side in ('before', 'after'):
                for region in change.get(side, []):
                    value = region.get('image')
                    if isinstance(value, str) and value.startswith('/history/images/'):
                        region['image'] = prefix + value[1:]
    return result
