"""Convention: subtitle_text = the narration text (captions are timed from it); the short on-slide wording is lesson_plan.json "slides".

Writes the POC lesson packages (lesson.csv + lesson_plan.json) for Class 7 Science, Nutrition in Plants / Photosynthesis,
in English, Hindi and Marathi:  python docs/poc/build_poc_content.py

The texts are DRAFTS for academic review. The Hindi and Marathi texts need a native-speaker reviewer before approval."""

import csv
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
VISUAL = [
    "A seed growing into a tree, time-lapse style",
    "Two groups: plants make food (autotrophs), animals and humans eat (heterotrophs)",
    "A leaf cross-section showing stomata and chloroplasts",
    "A chloroplast with chlorophyll absorbing sunlight",
    "Three arrows into a leaf: sunlight, water from the roots, carbon dioxide from the air",
    "The word equation with animated arrows",
    "Glucose and starch stored in a potato, oxygen leaving the leaf",
    "Steps of the iodine test on a leaf with the colour change",
    "Forest, clean air and people breathing",
    "Summary diagram with all inputs and outputs, then a question",
]

DATA = {
    "en-IN": {
        "title": "How plants make food: photosynthesis",
        "objectives": ["Define photosynthesis", "Name the raw materials and products", "Explain the role of chlorophyll and stomata", "Describe the iodine test for starch"],
        "rows": [
            ("Introduction", "Have you ever wondered how a tiny seed grows into a huge tree? Animals eat food to get energy, but plants do not eat. Plants make their own food, and they do it using sunlight. This wonderful process is called photosynthesis, and in this lesson we will learn how it works.", "Plants make their own food."),
            ("Autotrophs", "Living things that make their own food are called autotrophs. Green plants are autotrophs. Animals and humans cannot make their own food, so they depend on plants and other animals. That is why they are called heterotrophs. Almost all the food we eat comes, directly or indirectly, from plants that make food by photosynthesis.", "Autotrophs and heterotrophs"),
            ("Where it happens", "Photosynthesis happens mostly in the leaves. If you look at a leaf closely, you will see tiny openings called stomata. Through the stomata, air enters and leaves the leaf. Inside the leaf cells there are small green parts called chloroplasts. These contain a green pigment called chlorophyll, which gives leaves their green colour.", "Leaves, stomata and chloroplasts"),
            ("Chlorophyll", "Chlorophyll is very important. It captures the energy of sunlight. Without chlorophyll, a leaf cannot use sunlight to make food. This is why photosynthesis takes place only in the green parts of a plant, and not in the roots, which are not green. Some plants have red or purple leaves, but they also contain chlorophyll, hidden by other colours.", "Chlorophyll captures sunlight"),
            ("Raw materials", "To make food, a plant needs three raw materials. The first is sunlight, which provides energy. The second is water, which the roots absorb from the soil and send up to the leaves through tiny tubes. The third is carbon dioxide, a gas from the air, which enters the leaf through the stomata.", "Sunlight, water and carbon dioxide"),
            ("The process", "Inside the chloroplasts, chlorophyll captures the energy of sunlight. This energy is used to change water and carbon dioxide into a sugar called glucose. At the same time, oxygen is released. We can write it like this: carbon dioxide plus water, in the presence of sunlight and chlorophyll, gives glucose plus oxygen.", "Carbon dioxide + water gives glucose + oxygen"),
            ("Products", "The plant makes two products. The first is glucose, a type of sugar, which gives the plant energy to grow. The extra glucose is stored as starch, in places like potatoes and rice grains. The second product is oxygen. It leaves the leaf through the stomata and goes into the air. We and other animals breathe this oxygen.", "Glucose, starch and oxygen"),
            ("Testing for starch", "We can show that a leaf has made starch with a simple test. Boil the leaf in alcohol to remove its green colour, then pour a few drops of iodine solution on it. If starch is present, the leaf turns blue black. A leaf kept in the dark does not turn blue black, because without light it could not make starch.", "The iodine test for starch"),
            ("Why it matters", "Photosynthesis is important for all life on Earth. It gives food to plants, and through plants to animals and humans. It also keeps the air balanced, because plants take in carbon dioxide and give out oxygen. Forests and green spaces help keep our air fresh. That is why we should protect plants and plant more trees.", "Why photosynthesis matters"),
            ("Summary", "Let us remember. Plants make their own food by photosynthesis. It happens in the green leaves, using chlorophyll. The raw materials are sunlight, water and carbon dioxide. The products are glucose and oxygen. Extra glucose is stored as starch. Now think: what would happen to life on Earth if plants stopped making food?", "Summary: how plants make food"),
        ],
    },
    "hi-IN": {
        "title": "पौधे भोजन कैसे बनाते हैं: प्रकाश संश्लेषण",
        "objectives": ["प्रकाश संश्लेषण की परिभाषा बताना", "कच्ची सामग्री और उत्पादों के नाम बताना", "क्लोरोफिल और रंध्रों की भूमिका समझाना", "स्टार्च की आयोडीन जाँच का वर्णन करना"],
        "rows": [
            ("परिचय", "क्या आपने कभी सोचा है कि एक छोटा-सा बीज इतना बड़ा पेड़ कैसे बन जाता है? जानवर भोजन खाकर ऊर्जा पाते हैं, लेकिन पौधे भोजन नहीं खाते। पौधे अपना भोजन खुद बनाते हैं, और इसके लिए वे सूर्य के प्रकाश का उपयोग करते हैं। इस अद्भुत प्रक्रिया को प्रकाश संश्लेषण कहते हैं। इस पाठ में हम समझेंगे कि यह कैसे होता है।", "पौधे अपना भोजन खुद बनाते हैं।"),
            ("स्वपोषी", "जो जीव अपना भोजन स्वयं बनाते हैं, उन्हें स्वपोषी कहते हैं। हरे पौधे स्वपोषी होते हैं। जानवर और मनुष्य अपना भोजन स्वयं नहीं बना सकते, इसलिए वे पौधों और दूसरे जानवरों पर निर्भर रहते हैं। उन्हें परपोषी कहते हैं। हम जो भोजन खाते हैं, वह लगभग सारा सीधे या परोक्ष रूप से उन पौधों से आता है जो प्रकाश संश्लेषण से भोजन बनाते हैं।", "स्वपोषी और परपोषी"),
            ("कहाँ होता है", "प्रकाश संश्लेषण मुख्य रूप से पत्तियों में होता है। पत्ती को ध्यान से देखें तो उस पर छोटे-छोटे छिद्र दिखते हैं, जिन्हें रंध्र कहते हैं। रंध्रों से हवा पत्ती के अंदर आती और बाहर जाती है। पत्ती की कोशिकाओं में हरे रंग के छोटे भाग होते हैं, जिन्हें क्लोरोप्लास्ट कहते हैं। इनमें क्लोरोफिल नामक हरा वर्णक होता है, जिससे पत्तियाँ हरी दिखती हैं।", "पत्तियाँ, रंध्र और क्लोरोप्लास्ट"),
            ("क्लोरोफिल", "क्लोरोफिल बहुत महत्वपूर्ण है। यह सूर्य के प्रकाश की ऊर्जा को ग्रहण करता है। क्लोरोफिल के बिना पत्ती सूर्य के प्रकाश से भोजन नहीं बना सकती। इसीलिए प्रकाश संश्लेषण पौधे के केवल हरे भागों में होता है, जड़ों में नहीं, क्योंकि जड़ें हरी नहीं होतीं। कुछ पौधों की पत्तियाँ लाल या बैंगनी होती हैं, लेकिन उनमें भी क्लोरोफिल होता है, जो दूसरे रंगों के पीछे छिपा रहता है।", "क्लोरोफिल सूर्य का प्रकाश ग्रहण करता है"),
            ("कच्ची सामग्री", "भोजन बनाने के लिए पौधे को तीन कच्ची सामग्रियाँ चाहिए। पहली है सूर्य का प्रकाश, जो ऊर्जा देता है। दूसरी है पानी, जिसे जड़ें मिट्टी से सोखती हैं और छोटी-छोटी नलिकाओं से पत्तियों तक पहुँचाती हैं। तीसरी है कार्बन डाइऑक्साइड, जो हवा में पाई जाने वाली एक गैस है और रंध्रों के रास्ते पत्ती में प्रवेश करती है।", "प्रकाश, पानी और कार्बन डाइऑक्साइड"),
            ("प्रक्रिया", "क्लोरोप्लास्ट के अंदर क्लोरोफिल सूर्य के प्रकाश की ऊर्जा को ग्रहण करता है। इस ऊर्जा से पानी और कार्बन डाइऑक्साइड मिलकर ग्लूकोज नामक शर्करा बनाते हैं। इसके साथ ऑक्सीजन भी निकलती है। इसे हम इस प्रकार लिख सकते हैं: कार्बन डाइऑक्साइड और पानी, सूर्य के प्रकाश और क्लोरोफिल की उपस्थिति में, ग्लूकोज और ऑक्सीजन बनाते हैं।", "कार्बन डाइऑक्साइड + पानी से ग्लूकोज + ऑक्सीजन"),
            ("उत्पाद", "इस क्रिया से दो चीज़ें बनती हैं। पहली है ग्लूकोज, एक प्रकार की शर्करा, जो पौधे को बढ़ने की ऊर्जा देती है। अतिरिक्त ग्लूकोज स्टार्च के रूप में जमा हो जाता है, जैसे आलू और चावल के दानों में। दूसरी चीज़ है ऑक्सीजन। यह रंध्रों से निकलकर हवा में चली जाती है। हम और दूसरे जानवर इसी ऑक्सीजन में साँस लेते हैं।", "ग्लूकोज, स्टार्च और ऑक्सीजन"),
            ("स्टार्च की जाँच", "एक आसान परीक्षण से हम दिखा सकते हैं कि पत्ती ने स्टार्च बनाया है। पत्ती को अल्कोहल में उबालकर उसका हरा रंग हटा दें, फिर उस पर आयोडीन के घोल की कुछ बूँदें डालें। यदि स्टार्च है, तो पत्ती नीली-काली हो जाती है। अँधेरे में रखी पत्ती नीली-काली नहीं होती, क्योंकि प्रकाश के बिना वह स्टार्च नहीं बना पाई।", "स्टार्च की आयोडीन जाँच"),
            ("महत्व", "प्रकाश संश्लेषण पृथ्वी के सभी जीवों के लिए महत्वपूर्ण है। यह पौधों को भोजन देता है, और पौधों के माध्यम से जानवरों और मनुष्यों को भी। यह हवा का संतुलन भी बनाए रखता है, क्योंकि पौधे कार्बन डाइऑक्साइड लेते हैं और ऑक्सीजन छोड़ते हैं। जंगल और हरे-भरे स्थान हमारी हवा को ताज़ा रखते हैं। इसलिए हमें पौधों की रक्षा करनी चाहिए और अधिक पेड़ लगाने चाहिए।", "प्रकाश संश्लेषण क्यों महत्वपूर्ण है"),
            ("सारांश", "आइए याद करें। पौधे प्रकाश संश्लेषण से अपना भोजन खुद बनाते हैं। यह क्रिया हरी पत्तियों में क्लोरोफिल की मदद से होती है। कच्ची सामग्रियाँ हैं सूर्य का प्रकाश, पानी और कार्बन डाइऑक्साइड। उत्पाद हैं ग्लूकोज और ऑक्सीजन। अतिरिक्त ग्लूकोज स्टार्च के रूप में जमा होता है। अब सोचिए: अगर पौधे भोजन बनाना बंद कर दें, तो पृथ्वी पर जीवन का क्या होगा?", "सारांश: पौधे भोजन कैसे बनाते हैं"),
        ],
    },
    "mr-IN": {
        "title": "वनस्पती अन्न कसे तयार करतात: प्रकाशसंश्लेषण",
        "objectives": ["प्रकाशसंश्लेषणाची व्याख्या सांगणे", "कच्चा माल आणि तयार होणाऱ्या गोष्टींची नावे सांगणे", "क्लोरोफिल आणि पर्णरंध्रांची भूमिका स्पष्ट करणे", "स्टार्चची आयोडीन चाचणी वर्णन करणे"],
        "rows": [
            ("प्रस्तावना", "एवढ्या लहान बीमधून एवढे मोठे झाड कसे तयार होते, याचा तुम्ही कधी विचार केला आहे का? प्राणी अन्न खाऊन ऊर्जा मिळवतात, पण वनस्पती अन्न खात नाहीत. वनस्पती स्वतःचे अन्न स्वतः तयार करतात, आणि त्यासाठी त्या सूर्यप्रकाशाचा वापर करतात. या अद्भुत क्रियेला प्रकाशसंश्लेषण म्हणतात. या पाठात आपण ही क्रिया कशी होते ते समजून घेऊ.", "वनस्पती स्वतःचे अन्न तयार करतात."),
            ("स्वयंपोषी", "जे सजीव स्वतःचे अन्न स्वतः तयार करतात, त्यांना स्वयंपोषी म्हणतात. हिरव्या वनस्पती स्वयंपोषी असतात. प्राणी आणि माणसे स्वतःचे अन्न तयार करू शकत नाहीत, म्हणून ती वनस्पती आणि इतर प्राण्यांवर अवलंबून असतात. त्यांना परपोषी म्हणतात. आपण जे अन्न खातो, ते जवळजवळ सर्व थेट किंवा अप्रत्यक्षपणे प्रकाशसंश्लेषणाने अन्न तयार करणाऱ्या वनस्पतींकडून मिळते.", "स्वयंपोषी आणि परपोषी"),
            ("हे कुठे होते", "प्रकाशसंश्लेषण प्रामुख्याने पानांमध्ये होते. पान जवळून पाहिले तर त्यावर लहान छिद्रे दिसतात, त्यांना पर्णरंध्रे म्हणतात. पर्णरंध्रांमधून हवा पानात येते आणि बाहेर जाते. पानाच्या पेशींमध्ये हिरव्या रंगाचे लहान भाग असतात, त्यांना हरितलवके म्हणतात. त्यांच्यात क्लोरोफिल नावाचे हिरवे रंगद्रव्य असते, त्यामुळे पाने हिरवी दिसतात.", "पाने, पर्णरंध्रे आणि हरितलवके"),
            ("क्लोरोफिल", "क्लोरोफिल खूप महत्त्वाचे आहे. ते सूर्यप्रकाशाची ऊर्जा ग्रहण करते. क्लोरोफिलशिवाय पान सूर्यप्रकाशापासून अन्न तयार करू शकत नाही. म्हणूनच प्रकाशसंश्लेषण वनस्पतीच्या फक्त हिरव्या भागांमध्ये होते, मुळांमध्ये नाही, कारण मुळे हिरवी नसतात. काही वनस्पतींची पाने लाल किंवा जांभळी असतात, पण त्यांच्यातही क्लोरोफिल असते, जे इतर रंगांमागे लपलेले असते.", "क्लोरोफिल सूर्यप्रकाश ग्रहण करते"),
            ("कच्चा माल", "अन्न तयार करण्यासाठी वनस्पतीला तीन कच्चा माल लागतो. पहिला म्हणजे सूर्यप्रकाश, जो ऊर्जा देतो. दुसरा म्हणजे पाणी, जे मुळे जमिनीतून शोषून घेतात आणि लहान नलिकांमधून पानांपर्यंत पोहोचवतात. तिसरा म्हणजे कार्बन डायऑक्साइड, हवेतील एक वायू, जो पर्णरंध्रांमधून पानात प्रवेश करतो.", "सूर्यप्रकाश, पाणी आणि कार्बन डायऑक्साइड"),
            ("क्रिया", "हरितलवकांच्या आत क्लोरोफिल सूर्यप्रकाशाची ऊर्जा ग्रहण करते. या ऊर्जेने पाणी आणि कार्बन डायऑक्साइड यांच्यापासून ग्लुकोज नावाची साखर तयार होते. त्याच वेळी ऑक्सिजन बाहेर पडतो. हे आपण असे लिहू शकतो: कार्बन डायऑक्साइड आणि पाणी, सूर्यप्रकाश आणि क्लोरोफिलच्या उपस्थितीत, ग्लुकोज आणि ऑक्सिजन तयार करतात.", "कार्बन डायऑक्साइड + पाणी = ग्लुकोज + ऑक्सिजन"),
            ("तयार होणाऱ्या गोष्टी", "या क्रियेतून दोन गोष्टी तयार होतात. पहिली म्हणजे ग्लुकोज, एक प्रकारची साखर, जी वनस्पतीला वाढण्यासाठी ऊर्जा देते. जादा ग्लुकोज स्टार्चच्या रूपात साठवला जातो, जसे बटाटा आणि तांदळाच्या दाण्यांमध्ये. दुसरी गोष्ट म्हणजे ऑक्सिजन. तो पर्णरंध्रांमधून बाहेर पडून हवेत जातो. आपण आणि इतर प्राणी हाच ऑक्सिजन श्वासावाटे घेतो.", "ग्लुकोज, स्टार्च आणि ऑक्सिजन"),
            ("स्टार्चची चाचणी", "एका सोप्या चाचणीने आपण दाखवू शकतो की पानाने स्टार्च तयार केला आहे. पान अल्कोहोलमध्ये उकळून त्याचा हिरवा रंग काढून टाका, मग त्यावर आयोडीनच्या द्रावणाचे काही थेंब टाका. स्टार्च असेल तर पान निळसर काळे होते. अंधारात ठेवलेले पान निळसर काळे होत नाही, कारण प्रकाशाशिवाय ते स्टार्च तयार करू शकले नाही.", "स्टार्चची आयोडीन चाचणी"),
            ("महत्त्व", "प्रकाशसंश्लेषण पृथ्वीवरील सर्व सजीवांसाठी महत्त्वाचे आहे. ते वनस्पतींना अन्न देते, आणि वनस्पतींमार्फत प्राण्यांना व माणसांनाही. ते हवेचा समतोलही राखते, कारण वनस्पती कार्बन डायऑक्साइड घेतात आणि ऑक्सिजन सोडतात. जंगले आणि हिरवीगार ठिकाणे आपली हवा ताजी ठेवतात. म्हणून आपण वनस्पतींचे संरक्षण केले पाहिजे आणि जास्त झाडे लावली पाहिजेत.", "प्रकाशसंश्लेषण का महत्त्वाचे आहे"),
            ("सारांश", "चला, लक्षात ठेवूया. वनस्पती प्रकाशसंश्लेषणाने स्वतःचे अन्न स्वतः तयार करतात. ही क्रिया हिरव्या पानांमध्ये क्लोरोफिलच्या मदतीने होते. कच्चा माल म्हणजे सूर्यप्रकाश, पाणी आणि कार्बन डायऑक्साइड. तयार होणाऱ्या गोष्टी म्हणजे ग्लुकोज आणि ऑक्सिजन. जादा ग्लुकोज स्टार्चच्या रूपात साठवला जातो. आता विचार करा: वनस्पतींनी अन्न तयार करणे थांबवले, तर पृथ्वीवरील जीवनाचे काय होईल?", "सारांश: वनस्पती अन्न कसे तयार करतात"),
        ],
    },
}

BULLETS = {
    "en-IN": [
        ["Animals eat food for energy", "Plants make their own food", "The process is photosynthesis"],
        ["Autotrophs make their own food", "Heterotrophs depend on others", "Our food comes from plants"],
        ["Leaves: where it happens", "Stomata: tiny openings", "Chloroplasts hold chlorophyll"],
        ["Chlorophyll is a green pigment", "It captures sunlight energy", "Only green parts make food"],
        ["Sunlight: energy", "Water: from the roots", "Carbon dioxide: from the air"],
        ["Chlorophyll captures light energy", "Water and carbon dioxide become glucose", "Oxygen is released"],
        ["Glucose: energy to grow", "Extra glucose: stored as starch", "Oxygen: released into the air"],
        ["Boil the leaf in alcohol", "Add iodine solution", "Blue-black means starch"],
        ["Food for plants and animals", "Balances carbon dioxide and oxygen", "Protect plants, plant trees"],
        ["Raw materials: sunlight, water, carbon dioxide", "Products: glucose and oxygen", "Extra glucose is stored as starch"],
    ],
    "hi-IN": [
        ["जानवर भोजन खाते हैं", "पौधे अपना भोजन खुद बनाते हैं", "इस क्रिया का नाम प्रकाश संश्लेषण"],
        ["स्वपोषी: अपना भोजन खुद बनाते हैं", "परपोषी: दूसरों पर निर्भर", "हमारा भोजन पौधों से आता है"],
        ["पत्तियाँ: यहाँ होता है", "रंध्र: छोटे छिद्र", "क्लोरोप्लास्ट में क्लोरोफिल"],
        ["क्लोरोफिल: हरा वर्णक", "सूर्य की ऊर्जा ग्रहण करता है", "केवल हरे भाग भोजन बनाते हैं"],
        ["प्रकाश: ऊर्जा देता है", "पानी: जड़ों से", "कार्बन डाइऑक्साइड: हवा से"],
        ["क्लोरोफिल प्रकाश की ऊर्जा लेता है", "पानी और कार्बन डाइऑक्साइड से ग्लूकोज", "ऑक्सीजन निकलती है"],
        ["ग्लूकोज: बढ़ने की ऊर्जा", "अतिरिक्त ग्लूकोज: स्टार्च", "ऑक्सीजन: हवा में जाती है"],
        ["पत्ती को अल्कोहल में उबालें", "आयोडीन के घोल की बूँदें डालें", "नीली-काली: स्टार्च है"],
        ["पौधों और जानवरों को भोजन", "कार्बन डाइऑक्साइड और ऑक्सीजन का संतुलन", "पौधों की रक्षा करें, पेड़ लगाएँ"],
        ["कच्ची सामग्री: प्रकाश, पानी, कार्बन डाइऑक्साइड", "उत्पाद: ग्लूकोज और ऑक्सीजन", "अतिरिक्त ग्लूकोज स्टार्च बनता है"],
    ],
    "mr-IN": [
        ["प्राणी अन्न खातात", "वनस्पती स्वतःचे अन्न बनवतात", "या क्रियेला प्रकाशसंश्लेषण म्हणतात"],
        ["स्वयंपोषी: स्वतः अन्न बनवतात", "परपोषी: इतरांवर अवलंबून", "आपले अन्न वनस्पतींपासून"],
        ["पाने: येथे क्रिया होते", "पर्णरंध्रे: लहान छिद्रे", "हरितलवकांत क्लोरोफिल"],
        ["क्लोरोफिल: हिरवे रंगद्रव्य", "सूर्यप्रकाशाची ऊर्जा ग्रहण करते", "फक्त हिरवे भाग अन्न बनवतात"],
        ["सूर्यप्रकाश: ऊर्जा", "पाणी: मुळांपासून", "कार्बन डायऑक्साइड: हवेतून"],
        ["क्लोरोफिल प्रकाशाची ऊर्जा घेते", "पाणी आणि कार्बन डायऑक्साइडपासून ग्लुकोज", "ऑक्सिजन बाहेर पडतो"],
        ["ग्लुकोज: वाढण्यासाठी ऊर्जा", "जादा ग्लुकोज: स्टार्च", "ऑक्सिजन: हवेत जातो"],
        ["पान अल्कोहोलमध्ये उकळा", "आयोडीनचे थेंब टाका", "निळसर काळे: स्टार्च आहे"],
        ["वनस्पती व प्राण्यांना अन्न", "कार्बन डायऑक्साइड-ऑक्सिजन समतोल", "वनस्पती वाचवा, झाडे लावा"],
        ["कच्चा माल: सूर्यप्रकाश, पाणी, कार्बन डायऑक्साइड", "तयार: ग्लुकोज आणि ऑक्सिजन", "जादा ग्लुकोज: स्टार्च"],
    ],
}

def _eq(a, b, c, d, note):
    return {"layout": "equation", "diagram": {"terms": [a, "+", b, "→", c, "+", d], "note": note}}


def _flow(steps, roles=None):
    return {"layout": "flow", "diagram": {"steps": [{"label": x, **({"role": roles[i]} if roles and roles[i] else {})} for i, x in enumerate(steps)]}}


def _cmp(lt, lp, rt, rp):
    return {"layout": "compare", "diagram": {"left": {"title": lt, "points": lp}, "right": {"title": rt, "points": rp}}}


# animated layouts for selected slides (slide number -> layout and diagram); other slides show their bullets one by one
LAYOUT_SLIDES = {
    "en-IN": {2: _cmp("Autotrophs", ["Make their own food", "Green plants"], "Heterotrophs", ["Depend on others", "Animals and humans"]),
              6: _eq("Carbon dioxide", "Water", "Glucose", "Oxygen", "in sunlight, with chlorophyll"),
              8: _flow(["Boil the leaf in alcohol", "Add iodine solution", "Blue-black means starch"]),
              10: _flow(["Sunlight, water, carbon dioxide", "Chlorophyll in the leaf", "Glucose and oxygen"], ["input", None, "output"])},
    "hi-IN": {2: _cmp("स्वपोषी", ["अपना भोजन खुद बनाते हैं", "हरे पौधे"], "परपोषी", ["दूसरों पर निर्भर", "जानवर और मनुष्य"]),
              6: _eq("कार्बन डाइऑक्साइड", "पानी", "ग्लूकोज", "ऑक्सीजन", "सूर्य के प्रकाश में, क्लोरोफिल की मदद से"),
              8: _flow(["पत्ती को अल्कोहल में उबालें", "आयोडीन का घोल डालें", "नीली-काली = स्टार्च"]),
              10: _flow(["प्रकाश, पानी, कार्बन डाइऑक्साइड", "पत्ती में क्लोरोफिल", "ग्लूकोज और ऑक्सीजन"], ["input", None, "output"])},
    "mr-IN": {2: _cmp("स्वयंपोषी", ["स्वतः अन्न बनवतात", "हिरव्या वनस्पती"], "परपोषी", ["इतरांवर अवलंबून", "प्राणी आणि माणसे"]),
              6: _eq("कार्बन डायऑक्साइड", "पाणी", "ग्लुकोज", "ऑक्सिजन", "सूर्यप्रकाश आणि क्लोरोफिलच्या मदतीने"),
              8: _flow(["पान अल्कोहोलमध्ये उकळा", "आयोडीनचे द्रावण टाका", "निळसर काळे = स्टार्च"]),
              10: _flow(["सूर्यप्रकाश, पाणी, कार्बन डायऑक्साइड", "पानातील क्लोरोफिल", "ग्लुकोज आणि ऑक्सिजन"], ["input", None, "output"])},
}

QUIZ = {
    "en-IN": [{"question": "Which pigment in a leaf captures sunlight?", "options": ["Chlorophyll", "Starch", "Glucose"], "answer": "Chlorophyll"},
              {"question": "Name the two products of photosynthesis.", "answer": "Glucose and oxygen"}],
    "hi-IN": [{"question": "पत्ती का कौन-सा वर्णक सूर्य का प्रकाश ग्रहण करता है?", "options": ["क्लोरोफिल", "स्टार्च", "ग्लूकोज"], "answer": "क्लोरोफिल"},
              {"question": "प्रकाश संश्लेषण के दो उत्पादों के नाम बताइए।", "answer": "ग्लूकोज और ऑक्सीजन"}],
    "mr-IN": [{"question": "पानातील कोणते रंगद्रव्य सूर्यप्रकाश ग्रहण करते?", "options": ["क्लोरोफिल", "स्टार्च", "ग्लुकोज"], "answer": "क्लोरोफिल"},
              {"question": "प्रकाशसंश्लेषणातून तयार होणाऱ्या दोन गोष्टींची नावे सांगा.", "answer": "ग्लुकोज आणि ऑक्सिजन"}],
}

for lang, d in DATA.items():
    folder = OUT / lang
    folder.mkdir(exist_ok=True)
    with (folder / "lesson.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Slide", "Module", "voice_text", "subtitle_text", "visual_instruction"])
        for i, (module, voice, subtitle) in enumerate(d["rows"], 1):
            w.writerow([i, module, voice, voice, VISUAL[i - 1]])  # captions are timed from subtitle_text: use the narration text
    plan = {"title": d["title"], "language": lang, "learning_objectives": d["objectives"],
            "source_references": ["Class 7 Science, Chapter 1: Nutrition in Plants (draft; to be checked against the prescribed textbook)"],
            "slides": [{"slide": i, "headline": r[2].rstrip("."), "bullets": BULLETS[lang][i - 1], **LAYOUT_SLIDES[lang].get(i, {})} for i, r in enumerate(d["rows"], 1)],
            "quiz": QUIZ[lang]}
    (folder / "lesson_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    words = sum(len(r[1].split()) for r in d["rows"])
    print(lang, len(d["rows"]), "slides,", words, "words, about", round(words / 130, 1), "min at 130 wpm")
