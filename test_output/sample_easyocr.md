vectors u and v. For one-dimensional vectors, this calculation is
shown in Eq. (1).
ccðu; vÞ ¼
P uivi  P ui
P vj
ﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃ
P u2
i  ðP uiÞ2
q
ﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃ
P v2
j  P vj
2
q
(1)
The Euclidean distances between each two of those vectors are
needed to process the HCA. Then there comes the need of Eq. (2) to
calculate the distance d between the row/column vectors u and v.
dðu; vÞ ¼ 1  ccðu; vÞ ¼ 1 
P uivi  P ui
P vj
ﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃ
P u2
i  ðP uiÞ2
q
ﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃﬃ
P v2
j  P vj
2
q
(2)
Brieﬂy speaking, the correlation matrix is calculated ﬁrstly, with
which the distance matrix can be calculated and used for the HCA
process. It is clear that HCA function needs to perform matrix cal-
culations, so there are mathematically limitations. If there are any
blank items in the data, or if the data matrix is a singular matrix,
HCA won’t be possible.
At the code level, this program uses SciPy to complete the
calculation process (Oliphant, 2007). This article only describes the
main idea instead of the speciﬁc calculation process, which can be
seen in code, at https://github.com/GeoPyTool/GeoPyTool/blob/
master/geopytool/Cluster.py .
Speciﬁcally, take Table 10 as an example, in which horizontal
rows and vertical columns are respectively considered as compar-
ative indexes. Each row is considered as a one-dimensional vector.
Euclidean distances between each two rows is used for the clus-
tering of left dendrogram shown in Fig. 2e. Similar process for each
column generates the dendrogram in the upper part of Fig. 2e. The
left dendrogram and the clustering for horizontal rows can be used
to separate ungrouped data into several groups, or to estimate the
dissimilarity of different rows. The upper dendrogram and the
clustering for vertical columns can be used to evaluate correlation
between different oxides or elements. The colored matrix in the
middle of Fig. 2e is a combination of the correlation matrix of rows
and columns.
Data in Table 10 contain different samples of a same volcanic
rock. It can be seen from Fig. 2e that these samples can be divided
into two groups by HCA, and SiO2 and other oxides is signiﬁcantly
dissimilar, which hints that there may be other sources of in-
gredients that affect the silica content.
5.4.3. Developing functions
Besides the routines mentioned above, new functions have been
added, including a clay-silt-sand classiﬁcation diagram (Fig. 2f and
data in Table 11), a 3D visualization function (Fig. 2g), and an Auto
function to generate all available calculations and plots for im-
ported data. GeoPyTool is still in development, more functions will
be gradually added.
5.5. Output ﬁles
GeoPyTool generates MS Excel XLSX and CSV ﬁles as output ﬁles
containing calculation result and generates diagrams in a PNG, SVG
or PDF format. The PNG format has become an International
Standard (ISO/IEC 15948:2003) and was classiﬁed as a World Wide
Web Consortium (W3C) recommendation in 2003 (Suyanto, 2008;
Web, 2010). This format is also supported by all mainstream
operating systems and provides images with a decent quality. The
SVG format is a widely deployed royalty-free graphic format
developed and maintained by the W3C SVG Working Group. It is
supported by all modern browsers for both desktop and mobile
computers (Quint, 2003). The PDF format is also widely used as a
universal format for documents and is used in GeoPyTool as a
complementary and extra format to SVG. Major graphic programs
Table 11
Sand-silt-clay data (vol.%) sample for GeoPyTool.
Label
Marker
Color
Size
Alpha
Style
Width
Clay
Sand
Silt
First Group
o
green
50
0.6
-
0.4
60.0
25.0
15.0
o
green
50
0.6
-
0.4
44.0
31.0
25.0
o
green
50
0.6
-
0.4
62.6
18.7
18.7
o
green
50
0.6
-
0.4
67.7
9.0
23.3
o
green
50
0.6
-
0.4
66.6
21.8
11.6
o
green
50
0.6
-
0.4
67.5
18.8
13.7
o
green
50
0.6
-
0.4
59.5
20.5
20
o
green
50
0.6
-
0.4
69.8
15.2
15
o
green
50
0.6
--
0.5
59.8
15.2
25
o
green
50
0.6
--
0.5
62.6
18.7
18.7
o
green
50
0.6
--
0.5
61.3
16.8
21.9
o
green
50
0.6
--
0.5
58.3
20
21.7
o
green
50
0.6
--
0.5
66.7
13.0
20.3
o
green
50
0.6
--
0.5
51.5
30.5
18.0
o
green
50
0.6
--
1.5
74.3
11.4
14.3
Second Group
d
blue
50
0.6
--
2.5
50.0
35.0
15.0
d
blue
50
0.6
--
3.5
54.4
18.4
27.2
d
blue
50
0.6
--
4.5
80.3
11.8
7.9
d
blue
50
0.6
--
5.5
51.3
27.1
21.6
d
blue
50
0.6
--
6.5
56.4
28.3
15.3
Third Group
D
grey
50
0.6
--
7.5
58.3
20.0
21.7
D
grey
50
0.6
--
8.5
66.7
18.0
15.3
D
grey
50
0.6
--
0.5
76.0
12.0
12.0
D
grey
50
0.6
--
0.5
71.9
13.5
14.6
D
grey
50
0.6
--
0.5
70.0
17.5
12.5
D
grey
50
0.6
--
0.5
69.8
11.0
19.2
The Last Group
s
red
50
0.6
--
0.5
51.8
48.2
0.0
s
red
50
0.6
--
0.5
40.8
59.2
0.0
s
red
50
0.6
--
1.5
61.0
39.0
0.0
s
red
50
0.6
--
2.5
40.0
60.0
0.0
Q.-Y. Yu et al. / Geoscience Frontiers 10 (2019) 1437e1447
1445