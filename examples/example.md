---
title: ret2win
description: A small GitBook conversion example
tags: [pwn, stack]
---

# ret2win

Redirect execution to **win**, using the `win()` function.

{% hint style="warning" %}
This overwrites the saved return pointer.
{% endhint %}

{% tabs %}
{% tab title="Python" %}
{% code title="exploit.py" lineNumbers="true" %}
```python
payload = b"A" * 52
```
{% endcode %}
{% endtab %}
{% tab title="Explanation" %}
The padding length is $4 \times 13$ bytes.
{% endtab %}
{% endtabs %}

{% file src="assets/ret2win.zip" caption="Download the challenge" %}

See [stack alignment](stack-alignment.md) next.
