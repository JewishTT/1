# -*- coding: utf-8 -*-
"""Section 0.12 inventory generator. Part 1: mapping + groups."""
M = [
 ("thecrowler","pzaino/thecrowler","Web/crawl"),
 ("spiderfoot","smICALLEF/spiderfoot","Web/crawl"),
 ("secureflow-intel","BarakMozesPro/secureflow-intel","Web/crawl"),
 ("estorides","grisuno/estorides","Web/crawl"),
 ("lazyaddon","grisuno/lazyaddon","Frameworks"),
 ("OnionSearch","megadose/OnionSearch","Tor/darkweb"),
 ("trident","tbckr/trident","Net"),
 ("seekr","seekr-osint/seekr","Frameworks"),
 ("osint-terminal","RojanSapkota/osint-terminal","Frameworks"),
 ("argus-cotcollective","cotcollective/argus","Frameworks"),
 ("osint-web-mcp","Johnz86/osint-web-mcp","Frameworks"),
 ("Aperture-OSINT-Workbench","petstuk/Aperture-OSINT-Workbench","Frameworks"),
 ("phantomsignal","getphantomsignal/phantomsignal","Frameworks"),
 ("The-3rd-Eye","Ordinary0x/The-3rd-Eye","Frameworks"),
 ("osint-search-tool","hasamba/osint-search-tool","Frameworks"),
 ("TraceMatrix","PanagiotisDrakatos/TraceMatrix","Frameworks"),
 ("Hostile-Command-Suite","cycloarcane/Hostile-Command-Suite","Frameworks"),
 ("TheBigBrother","chadi0x/TheBigBrother","Frameworks"),
 ("maigret","soxoj/maigret","Username/Email"),
 ("sherlock","sherlock-project/sherlock","Username/Email"),
 ("holehe","megadose/holehe","Username/Email"),
 ("user-scanner","kaifcodec/user-scanner","Username/Email"),
 ("mosint","alpkeskin/mosint","Username/Email"),
 ("WhoCord","Siv-nick/WhoCord","Username/Email"),
 ("OsintEye","atiilla/OsintEye","Username/Email"),
 ("Profil3r","Greyjedix/Profil3r","Username/Email"),
 ("gitsnitch","gruns/gitsnitch","Git-email"),
 ("gitrecon","atiilla/gitrecon","Git-email"),
 ("GitFive","mxrch/GitFive","Git-email"),
 ("github-email-extractor","toqulent/github-email-extractor","Git-email"),
 ("EmailFinder","elliott-diy/EmailFinder","Git-email"),
 ("gh-mailto","codeGROOVE-dev/gh-mailto","Git-email"),
 ("theHarvester","laramies/theHarvester","Domain/Email"),
 ("Sublist3r","aboul3la/Sublist3r","Domain/Email"),
 ("Mail-Hunter","CYB3R-G0D/Mail-Hunter","Domain/Email"),
 ("coldreach","dhruvmojila/coldreach","Domain/Email"),
 ("Email-Permutator","emeth-/Email-Permutator","Domain/Email"),
 ("MottaHunter","MottaSec/MottaHunter","Domain/Email"),
 ("EmailHarvester","maldevel/EmailHarvester","Domain/Email"),
 ("Gmail_Checker","Baga6312/Gmail_Checker","Domain/Email"),
 ("phoneinfoga","sundowndev/phoneinfoga","Phone"),
 ("phone-osint-framework","aegisceo/phone-osint-framework","Phone"),
 ("Phunter","N0rz3/Phunter","Phone"),
 ("SearchPhone","HackUnderway/SearchPhone","Phone"),
 ("ignorant","megadose/ignorant","Phone"),
 ("DIGI-NETRA","pwnxotus/DIGI-NETRA","Phone"),
 ("X-osint","TechWithTy/X-osint","Phone"),
 ("email2phonenumber","martinvigo/email2phonenumber","Phone"),
 ("EmailExtractWithProxyApp","psoman-star/EmailExtractWithProxyApp","Social/bulk"),
 ("mysterious-cyclopus","Iankulani/mysterious-cyclopus","Spec-ops bridge"),
 ("CyberStrikeAI","Ed1s0nZ/CyberStrikeAI","Spec-ops bridge"),
 ("Flippy","thecaticorn01/Flippy","Spec-ops bridge"),
 ("postexploitation-toolbox-android","timschneeb/postexploitation-toolbox-android","Spec-ops bridge"),
]

import io, os
donors = r'C:\Users\tim\Desktop\COGNITIVE\1\donors'
path = r'C:\Users\tim\Desktop\COGNITIVE\1\docs\architecture\donors\10-ZERO-LAYER.md'

groups, missing = {}, []
for d, up, g in M:
    ok = os.path.isdir(os.path.join(donors, d)) and len(os.listdir(os.path.join(donors, d))) > 1
    if not ok:
        missing.append(d)
    groups.setdefault(g, []).append((d, up, ok))

out = [u"\n## 0.12 Clone Inventory \u2014 \u043a\u043b\u043e\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0435 \u0434\u043e\u043d\u043e\u0440\u044b zero-layer\n",
       u"\u0412\u0441\u0435 \u0440\u0435\u043f\u043e\u0437\u0438\u0442\u043e\u0440\u0438\u0438 \u043a\u043b\u043e\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u044b \u0432 `donors/` (--depth 1, \u043f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043e 2026-09-21).\n"]
for g, items in groups.items():
    out.append(u"\n### %s\n" % g)
    out.append(u"| \u0414\u0438\u0440\u0435\u043a\u0442\u043e\u0440\u0438\u044f | \u0420\u0435\u043f\u043e\u0437\u0438\u0442\u043e\u0440\u0438\u0439 | \u0421\u0442\u0430\u0442\u0443\u0441 |")
    out.append(u"|---|---|---|")
    for d, up, ok in items:
        st = u"\u2705 \u043a\u043b\u043e\u043d\u0438\u0440\u043e\u0432\u0430\u043d" if ok else u"\u274c \u041d\u0415 \u041a\u041b\u041e\u041d\u0418\u0420\u041e\u0412\u0410\u041d"
        out.append(u"| %s | %s | %s |" % (d, up, st))

out.append(u"\n### \u041d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0435 URL (404 \u043d\u0430 2026-09-21)\n\n"
      u"| \u0417\u0430\u044f\u0432\u043b\u0435\u043d\u043d\u044b\u0439 URL | \u0420\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442 |\n|---|---|\n"
      u"| null3yte/mailhound | \u274c 404 (\u0443\u0434\u0430\u043b\u0451\u043d/\u043f\u0435\u0440\u0435\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d) |\n"
      u"| megadose/phone-number-search | \u274c 404 |\n"
      u"| int3lsec/intel-harvester | \u274c 404 \u2192 \u0437\u0430\u043c\u0435\u043d\u0430: maldevel/EmailHarvester |\n"
      u"| RichardBarron27/red-specter-specter-censor | \u274c 404 \u2192 threat-landscape (defensive KB, \u0431\u0435\u0437 \u0432\u0435\u043d\u0434\u043e\u0440\u0438\u043d\u0433\u0430) |\n"
      u"| mavhm/email2phonenumber | \u274c 404 \u2192 \u0430\u043a\u0442\u0443\u0430\u043b\u044c\u043d\u044b\u0439: martinvigo/email2phonenumber |\n"
      u"| georgedavila/gh-mailto | \u274c 404 \u2192 \u0430\u043a\u0442\u0443\u0430\u043b\u044c\u043d\u044b\u0439: codeGROOVE-dev/gh-mailto |\n")

tot = sum(len(v) for v in groups.values())
okn = sum(1 for v in groups.values() for _, _, ok in v if ok)
ndirs = len([x for x in os.listdir(donors) if os.path.isdir(os.path.join(donors, x))])
out.append(u"\n> \u0418\u0442\u043e\u0433\u043e: **%d/%d \u043a\u043b\u043e\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u043e**; \u0432 `donors/` \u0442\u0435\u043f\u0435\u0440\u044c **%d \u043f\u0430\u043f\u043e\u043a** (\u0431\u044b\u043b\u043e 53).\n" % (okn, tot, ndirs))

with io.open(path, 'a', encoding='utf-8') as f:
    f.write(u"\n".join(out))
print('MISSING:', missing if missing else 'none', '| dirs:', ndirs)

