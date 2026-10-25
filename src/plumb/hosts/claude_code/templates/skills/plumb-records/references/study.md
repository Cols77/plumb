# A study the owner asks for

A study is plumb's built-in explainer of part of the project, written from its
records. When the owner asks for one, in any words ("a study of how merges are
held", "explain the judge in a study"), you recognise it from what they mean;
"study the failing test" asks for no study. Do not look into how plumb makes
studies: these are the steps, in order.

1. `{plumb} study propose --asked --title <their topic> --why <one line>
   --depth diagrams`. The band offers the idea; the owner picks the depth there
   (or says not now). Tell them in one line it is offered; write nothing yet.
2. Once they picked, `{plumb} study candidates --json` lists it under
   `accepted` with its slug and depth.
3. `{plumb} study gather <slug> --json`: the records it is written from; none
   means no record covers it, which you say instead of writing.
4. Write it in plain words from those records only, a mermaid diagram only at
   depth `diagrams`, then
   `{plumb} study add <slug> --records <their IDs> --file <body.md>`.
   The band announces it; the owner reads it in the room when they choose.
   Never open the room.
