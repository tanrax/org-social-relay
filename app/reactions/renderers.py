from rest_framework.renderers import JSONRenderer
import json


class UTF8JSONRenderer(JSONRenderer):
    """
    JSON renderer that preserves UTF-8 characters (like emojis) instead of escaping them.
    """
    charset = 'utf-8'
    
    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return bytes()

        renderer_context = renderer_context or {}
        indent = self.get_indent(accepted_media_type, renderer_context)

        if indent is None:
            separators = (',', ':')
        else:
            separators = (',', ': ')

        ret = json.dumps(
            data,
            ensure_ascii=False,
            indent=indent,
            separators=separators
        )

        # Handle invalid surrogate characters by using 'surrogatepass' error handler
        return ret.encode('utf-8', errors='surrogatepass')
