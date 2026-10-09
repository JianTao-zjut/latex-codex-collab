// Run: node test_markdown.mjs (stdlib only).
import assert from 'node:assert/strict';
import {markdownHtml,markdownSelectionRange} from './vendor/latex-markdown.mjs';

const source = String.raw`# Notes

A **bold** word, $x_1^2$, and \(y+1\).

$$
T=\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}
$$

- item
- [x] done

| a | b |
| - | - |
| 1 | 2 |

> quote

~~~tex
$this_is_code$ <script>literal</script>
~~~

Inline code: ` + '`$also_code$`' + String.raw`

![image](<images/a b.png>)
![[Pasted image.png|200]]

[reference][link]

[link]: https://example.com

# Notes
`;
const html = markdownHtml(source);
assert(html.includes('<h1 id="markdown-heading-notes">Notes</h1>'));
assert(html.includes('<h1 id="markdown-heading-notes-1">Notes</h1>'));
assert(html.includes('<strong>bold</strong>'));
assert.equal((html.match(/class="katex"/g) || []).length, 3,'Render inline, parenthesized and display math.');
assert(!html.includes('katex-error'));
assert(html.includes('<table>') && html.includes('<blockquote>') && html.includes('type="checkbox"'));
assert(html.includes('<code class="language-tex">$this_is_code$ &lt;script&gt;literal&lt;/script&gt;'));
assert(html.includes('<code>$also_code$</code>'),'Never render math inside code.');
assert(html.includes('src="/markdown-resource?path=images%2Fa%20b.png"'));
assert(html.includes('src="/markdown-resource?path=Pasted%20image.png"') && html.includes('width="200"'));
assert(html.includes('href="https://example.com"'),'Reference links survive per-block rendering.');
assert(markdownHtml('<script>alert(1)</script>\n').includes('&lt;script&gt;'));
const blocks = [...html.matchAll(/data-source-from="(\d+)" data-source-to="(\d+)"/g)];
assert.equal(Number(blocks[0][1]),0);assert.equal(Number(blocks.at(-1)[2]),source.length);
for(let i=1;i<blocks.length;i++)assert.equal(blocks[i][1],blocks[i-1][2],'Source mapping must cover the entire original document in order.');
assert(!markdownHtml('Price: $5 and $10.').includes('katex'),'Currency is ordinary text.');
const adjacent = markdownHtml(String.raw`we have
$$
x
=
y
$$

Next

$$
a
=
b
$$

## Still a heading

$\(q_1\)$
`);
assert.equal((adjacent.match(/class="katex-display"/g)||[]).length,2,'Display math directly after prose cannot be swallowed by Setext heading parsing.');
assert(adjacent.includes('Still a heading') && !adjacent.includes('katex-error'));
console.log('PASS: Markdown headings, source positions, lists/tasks, tables, code isolation, math/matrices, reference links, local/Obsidian images and escaped authored HTML');

const prose='Before\n\nA **bold** word and a [link](https://example.com).\n\nAfter';
const begin=prose.indexOf('A **'),end=prose.indexOf('\n\nAfter');
const find=text=>markdownSelectionRange(prose,begin,end,text);
let selected=find('bold word');
assert.equal(prose.slice(selected.from,selected.to),'**bold** word','Crossing formatting edges retains balanced Markdown.');
selected=find('link');assert.equal(prose.slice(selected.from,selected.to),'[link](https://example.com)');
selected=find('ol');assert.equal(prose.slice(selected.from,selected.to),'ol','Partial formatted text maps to exact source letters.');
assert.equal(markdownSelectionRange('same same',0,9,'same'),null,'Repeated text is never guessed.');
assert.equal(markdownSelectionRange('one\n  two',0,10,'one two').to,9,'Whitespace normalization preserves source offsets.');
assert.equal(markdownSelectionRange('A <b>secret</b> B',0,17,'A secret B'),null,'Untrusted raw HTML is a matching barrier.');
assert.deepEqual(markdownSelectionRange('中文批注',0,4,'文批'),{from:1,to:3});
console.log('PASS: Preview selection source ranges, formatted/link boundaries, Unicode, whitespace and ambiguous/HTML rejection');
