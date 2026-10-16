const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const AVATAR_URL = '/assets/moki-listening-avatar.png?v=20261015';
const API_MODAL_DELAY_MS = matchMedia('(prefers-reduced-motion: reduce)').matches ? 250 : 1000;
const STORAGE_VERSION = 4;
const STATE_KEY = 'moki-web-state';
const PREFERENCE_KEY = 'moki-preferences';
const LOCALES = ['ko', 'en', 'zh', 'ja'];
const LANGUAGE_LABELS = { ko: '한국어', en: 'English', zh: '中文', ja: '日本語' };
const SPEECH_LOCALES = { ko: 'ko-KR', en: 'en-US', zh: 'zh-CN', ja: 'ja-JP' };
const LANGUAGE_DETECTED_MESSAGES = {
  ko: '한국어 입력을 감지해 화면과 답변 언어를 바꿔어요.',
  en: 'English detected. The page and reply language have been updated.',
  zh: '已检测到中文，页面和回答语言已更新。',
  ja: '日本語の入力を検出し、画面と回答の言語を変更しました。',
};
const CATEGORY_LABELS = {
  ko: { '커피': '커피', '차/논커피': '차·논커피', '디저트': '디저트', '주류': '주류', '원두': '원두' },
  en: { '커피': 'Coffee', '차/논커피': 'Tea & non-coffee', '디저트': 'Dessert', '주류': 'Alcohol', '원두': 'Beans' },
  zh: { '커피': '咖啡', '차/논커피': '茶·非咖啡', '디저트': '甜点', '주류': '酒类', '원두': '咖啡豆' },
  ja: { '커피': 'コーヒー', '차/논커피': 'お茶・ノンコーヒー', '디저트': 'デザート', '주류': 'お酒', '원두': 'コーヒー豆' },
};
const MENU_NAMES = {
  zh: {
    M01: '浓缩咖啡', M02: '美式咖啡', M03: '拿铁', M04: '卡布奇诺', M05: '馥芮白', M06: '香草拿铁', M07: 'Goun-gyeol 奶油拿铁', M08: '黑巧摩卡',
    M09: '冷萃咖啡', M10: '冷萃拿铁', M11: '埃塞俄比亚手冲咖啡', M12: '低因手冲咖啡', M13: '抹茶拿铁', M14: '巧克力拿铁', M15: '宝城红茶奶茶', M16: '柚子茶', M17: '路易波士茶',
    M18: '黄油盐面包', M20: '巴斯克芝士蛋糕', M21: '杯装提拉米苏', M23: '招牌拼配咖啡豆 200克', M24: '埃塞俄比亚咖啡豆 200克', M25: '低因咖啡豆 200克', M26: '五味子茶', M27: '红枣姜茶',
    M28: '药果（2个）', M29: '艾草糯米糕（4个）', M32: '柚子烧酒嗨棒', M33: '五味子烧酒气泡酒', M34: '威士忌嗨棒', M35: '浓缩咖啡马天尼', M36: '拉格啤酒', M37: '招牌红葡萄酒',
  },
  ja: {
    M01: 'エスプレッソ', M02: 'アメリカーノ', M03: 'カフェラテ', M04: 'カプチーノ', M05: 'フラットホワイト', M06: 'バニララテ', M07: 'ゴウンギョル・クリームラテ', M08: 'ダークカフェモカ',
    M09: 'コールドブリュー', M10: 'コールドブリューラテ', M11: 'エチオピア・フィルターコーヒー', M12: 'デカフェ・フィルターコーヒー', M13: '抹茶ラテ', M14: 'チョコレートラテ', M15: '宝城紅茶ミルクティー', M16: '柚子茶', M17: 'ルイボスティー',
    M18: 'バター塩パン', M20: 'バスクチーズケーキ', M21: 'カップティラミス', M23: 'ハウスブレンド豆 200g', M24: 'エチオピア豆 200g', M25: 'デカフェ豆 200g', M26: 'オミジャ茶', M27: 'ナツメ生姜茶',
    M28: 'ヤックァ 2個', M29: 'よもぎインジョルミ 4個', M32: '柚子焼酎ハイボール', M33: 'オミジャ焼酎スプリッツ', M34: 'ウイスキーハイボール', M35: 'エスプレッソマティーニ', M36: 'ラガービール', M37: 'ハウス赤ワイン',
  },
};

const I18N = {
  ko: {
    batchProgress: '복합 주문 {current}/{total} · 옵션 확인 중', batchPending: '새 메시지 전에 나머지 메뉴를 순서대로 확인하거나 취소해 주세요.', cancelBatch: '나머지 옵션 선택 취소', batchCancelled: '나머지 메뉴의 옵션 선택을 취소했어요.',
    staffCodeChatPrompt: '직원 확인 영역으로 이동해 4자리 직원 코드를 입력해 주세요.',
    benefitCheckResult: '멤버십·쿠폰·포인트 확인 결과', noLinkedBenefits: '연결된 혜택이 없어 할인은 0원입니다.', beforeDiscount: '할인 전 금액', discountAmount: '할인', afterDiscount: '할인 후 금액', demoPaymentComplete: '시연 결제 완료', paidAmount: '최종 결제액', benefitApplied: '멤버십·혜택 적용', benefitNotApplied: '연결된 혜택 없음', orderNumberLabel: '주문번호',
    receiptCallout: '{number}번 손님, 잠시만 기다려 주세요!', receiptItems: '주문 메뉴', subtotal: '소계', demoReceiptLabel: '시연 결제 영수증',
    documentTitle: '모키 커피바', skipToChat: '대화창으로 바로가기', brandHome: '모키 커피바 홈', brandTagline: '한옥에서 천천히 고르는 한 잔',
    checkingContent: '콘텐츠 확인 중', connectedDemo: '데이터 연결됨 · 화면 체험 모드', connectedAI: '데이터·AI 연결 준비됨', keyNeeded: '데이터 연결됨 · API 키 필요', connectionError: '연결 확인 필요',
    easyView: '손쉬운 보기', apiKey: 'API 키', apiKeyChange: 'OpenAI API 키 변경', apiKeyEnter: 'OpenAI API 키 입력',
    heroTitle: '오늘의 한 잔을<br>천천히 골라보세요.', heroDescription: '메뉴 추천부터 옵션과 알레르기 확인까지, 모키가 데이터에 근거해 도와드릴게요.', talkToMoki: '모키와 대화하기', heroAlt: '커피를 들고 인사하는 모키',
    photoMenu: '사진 메뉴판', photoMenuNote: '데이터 파일에 포함된 대표 이미지 33장', menuCategories: '메뉴 분류', menuLoading: '메뉴를 준비하고 있어요.', conversationTitle: '모키와 대화하기', listenAnswer: '답변 듣기', messageLabel: '모키에게 보낼 메시지', messagePlaceholder: '예: 산미가 적고 고소한 커피를 추천해 주세요', send: '보내기', chatHelper: '가격과 옵션은 서버가 메뉴 데이터와 다시 확인합니다.',
    settings: '이용 설정', tableNumber: '좌석 번호', tableOption: '{n}번 테이블', staffCodeLabel: '주류 구매 직원 확인 코드', staffCodePlaceholder: '4자리 코드를 입력해 주세요', staffVerify: '직원 확인', cancelAlcohol: '주류 구매 취소', reset: '대화와 장바구니 초기화',
    orderDetails: '주문 내역', emptyCart: '아직 담긴 메뉴가 없습니다.', total: '합계', reviewOrder: '주문 검토하기', additionalOrder: '추가 주문하기', additionalOrderStarted: '이전 주문은 그대로 확정되어 있어요. 같은 좌석에서 추가 주문할 메뉴를 새 장바구니에 담아 주세요.', sourcesTitle: '답변에 참고한 정보', sourcesInitial: '대화를 시작하면 사용한 메뉴와 안내 자료가 표시됩니다.', sourcesEmpty: '이번 답변에는 별도의 메뉴 자료가 필요하지 않았습니다.',
    close: '닫기', easyViewTitle: '손쉬운 보기', easyViewDescription: '글자와 버튼을 크게 보고, 색상 대비를 높일 수 있어요.', largeText: '큰 글자', largeTextHelp: '전체 글자를 크게 표시', highContrast: '고대비', highContrastHelp: '글자와 배경을 더 선명하게', largeTargets: '큰 버튼', largeTargetsHelp: '누르기 쉽게 조작 영역을 확대', enableEasyView: '모두 켜기', resetView: '기본 보기', done: '완료',
    chooseOnce: '한 번에 선택', temperatureSize: '온도·크기', quantity: '수량', optionGuidance: '옵션을 바꾸지 않으면 기본값 그대로 담아요. 이 화면에서 한 번에 확인해 주세요.', expectedAmount: '예상 금액', cancel: '취소', addToCart: '장바구니에 담기', saveChanges: '변경 저장', optionsTitle: '옵션', allergens: '알레르기', noAllergens: '표시된 알레르기 정보 없음', defaultChoice: '기본', optionSelectTitle: '{name} 옵션 선택',
    checkoutTitle: '주문 한 번에 검토하기', serviceMode: '이용 방식', dineIn: '매장', takeout: '포장', cupChoice: '컵 선택', storeCup: '매장용 다회용컵', personalCup: '개인컵', disposableCup: '일회용컵', supplies: '필요한 비품', carrier: '캐리어', straw: '빨대', couponPoints: '쿠폰·포인트', noBenefits: '사용 가능한 쿠폰과 포인트가 없어요. 할인 0원', paymentMethod: '결제 방법', card: '카드', mobilePay: '모바일', gifticon: '기프티콘', splitPayment: '나눠 결제', noSplit: '나누지 않음', byItem: '메뉴별', equalSplit: '균등 분할', peopleCount: '인원수', receipt: '영수증', paperReceipt: '종이', digitalReceipt: '디지털', noReceipt: '안 받음', demoOnly: '시연용 기능', demoNotice: '실제 결제나 매장 접수는 이루어지지 않습니다.', finalTotal: '최종 금액', confirmDemoOrder: '시연용 주문 확정', orderComplete: '시연용 주문이 확정됐어요', orderNotSubmitted: '실제 결제나 매장 접수는 되지 않았습니다.', orderNumber: '시연용 주문번호: {number}',
    apiTitle: 'OpenAI API 키 연결', apiDescription: '대화를 시작하려면 API 키를 입력해 주세요. 키는 현재 페이지 메모리에만 두고 저장하지 않습니다.', apiKeyLabel: 'OpenAI API 키', apiPrivacy: '페이지를 새로고침하거나 닫으면 키가 사라집니다. 공용 기기에서는 사용하지 마세요.', startWithKey: '이 키로 시작하기', footer: '모키 커피바 · AI 응용 팀 프로젝트 · 가격과 영양 정보는 시연용 가상 설정입니다.',
    greeting: '안녕하세요, 모키예요. 먼저 편한 언어를 선택해 주세요. 취향과 피해야 할 재료를 메뉴 데이터에서 확인해 드릴게요. ☕', askMoki: '모키에게 묻기', chooseOptions: '옵션 선택하기', photoAlt: '{name} 대표 이미지', photoGallery: '메뉴 대표 이미지', imageFailed: '사진을 불러오지 못했어요', imageDescription: '엑셀 사진메뉴판의 AI 연출 대표 이미지', imageNote: '선택한 온도·크기·옵션에 따라 다를 수 있어요.',
    thinking: '메뉴 데이터를 확인하고 있어요…', requestFailed: '요청을 처리하지 못했습니다.', answerFailed: '답변을 불러오지 못했습니다.', checkConnection: '연결을 확인해 주세요.', responseFormat: '서버 응답 형식을 확인해 주세요.', keyRequired: 'API 키를 입력해 주세요.',
    staffNeeded: '직원 확인이 필요한 내용입니다. 직원을 부르겠습니다.', staffDone: '직원 나이 확인이 완료되었습니다. 주류 종류나 수량을 늘리면 다시 확인합니다.', alcoholInCart: '주류가 담겨 있어 직원 확인이 필요합니다.', staffRetry: '직원 확인된 요청 다시 시도', codeFourDigits: '4자리 직원 확인 코드를 입력해 주세요.', staffProcessing: '직원 확인을 처리하고 있습니다…', alcoholCancelled: '주류 구매 요청을 취소했어요. 다른 메뉴는 계속 편하게 고를 수 있어요.',
    edit: '수정', remove: '삭제', decrease: '수량 줄이기', increase: '수량 늘리기', cartUpdated: '장바구니가 바뀌었습니다.', addedToCart: '{name}을(를) 장바구니에 담았어요.', selectOptionsFor: '{name} 옵션 선택', cartActionFailed: '장바구니를 변경하지 못했어요.',
    suggestions: '함께 검토할 선택', sizeUp: '큰 사이즈 {size}로 변경 (+{price})', addShot: '샷 1개 추가 (+{price})', pairing: '{name}도 함께 볼까요? ({price})', accept: '적용', skip: '건너뛰기', suggestionAccepted: '적용했어요.', suggestionSkipped: '기본 선택을 유지해요.', pairingNext: '함께 고른 메뉴의 옵션을 이어서 확인해 주세요.',
    cartEmptyCheckout: '주문할 메뉴를 먼저 담아 주세요.', retryCheckout: '주문을 확정하지 못했어요. 연결과 선택을 확인한 뒤 다시 눌러 주세요.', confirming: '확정하는 중…', tableChanging: '좌석 번호를 변경하고 있어요…', tableChangeFailed: '좌석 번호를 변경하지 못했어요.', resetDone: '대화와 장바구니를 초기화했습니다.',
  },
  en: {
    batchProgress: 'Compound order {current}/{total} · reviewing options', batchPending: 'Review each remaining item in order or cancel before sending a new message.', cancelBatch: 'Cancel remaining options', batchCancelled: 'The remaining menu option reviews were cancelled.',
    staffCodeChatPrompt: 'Go to staff verification and have a staff member enter the 4-digit code.',
    benefitCheckResult: 'Membership, coupons & points', noLinkedBenefits: 'No benefits are connected. Discount ₩0.', beforeDiscount: 'Before discount', discountAmount: 'Discount', afterDiscount: 'After discount', demoPaymentComplete: 'Demo payment complete', paidAmount: 'Final demo payment', benefitApplied: 'Membership & benefits', benefitNotApplied: 'No connected benefits', orderNumberLabel: 'Order number',
    receiptCallout: 'Order {number}, please wait a moment!', receiptItems: 'Order items', subtotal: 'Subtotal', demoReceiptLabel: 'Demo payment receipt',
    documentTitle: 'Moki Coffee Bar', skipToChat: 'Skip to conversation', brandHome: 'Moki Coffee Bar home', brandTagline: 'Choose a quiet cup in a hanok', checkingContent: 'Checking content', connectedDemo: 'Data connected · demo mode', connectedAI: 'Data & AI ready', keyNeeded: 'Data connected · API key needed', connectionError: 'Check connection', easyView: 'Easy View', apiKey: 'API key', apiKeyChange: 'Change OpenAI API key', apiKeyEnter: 'Enter OpenAI API key',
    heroTitle: 'Take your time<br>choosing today’s cup.', heroDescription: 'Moki uses the menu data to help with recommendations, options, and allergen checks.', talkToMoki: 'Talk with Moki', heroAlt: 'Moki greeting you with a cup of coffee', photoMenu: 'Photo menu', photoMenuNote: '33 representative images included in the data file', menuCategories: 'Menu categories', menuLoading: 'Preparing the menu.', conversationTitle: 'Talk with Moki', listenAnswer: 'Listen', messageLabel: 'Message to Moki', messagePlaceholder: 'e.g. Recommend a smooth, low-acidity coffee', send: 'Send', chatHelper: 'Prices and options are checked again against the server menu data.',
    settings: 'Settings', tableNumber: 'Table number', tableOption: 'Table {n}', staffCodeLabel: 'Staff code for alcohol purchase', staffCodePlaceholder: 'Enter the 4-digit code', staffVerify: 'Staff verification', cancelAlcohol: 'Cancel alcohol purchase', reset: 'Reset chat and cart', orderDetails: 'Order', emptyCart: 'Your cart is empty.', total: 'Total', reviewOrder: 'Review order', additionalOrder: 'Start another order', additionalOrderStarted: 'Your previous order remains confirmed. Add items to a new cart for another order at the same table.', sourcesTitle: 'Sources used', sourcesInitial: 'Menu and guidance sources appear after you chat.', sourcesEmpty: 'No separate menu source was needed for this answer.',
    close: 'Close', easyViewTitle: 'Easy View', easyViewDescription: 'Make text and controls larger, or increase color contrast.', largeText: 'Large text', largeTextHelp: 'Enlarge text across the page', highContrast: 'High contrast', highContrastHelp: 'Make text and backgrounds clearer', largeTargets: 'Large controls', largeTargetsHelp: 'Increase tap target sizes', enableEasyView: 'Turn all on', resetView: 'Default view', done: 'Done', chooseOnce: 'CHOOSE ONCE', temperatureSize: 'Temperature & size', quantity: 'Quantity', optionGuidance: 'Keep the defaults to skip changes. Review everything once on this screen.', expectedAmount: 'Estimated amount', cancel: 'Cancel', addToCart: 'Add to cart', saveChanges: 'Save changes', optionsTitle: 'Options', allergens: 'Allergens', noAllergens: 'No allergen information listed', defaultChoice: 'Default', optionSelectTitle: 'Choose options for {name}',
    checkoutTitle: 'Review your order once', serviceMode: 'Service', dineIn: 'Dine in', takeout: 'Takeout', cupChoice: 'Cup', storeCup: 'Reusable store cup', personalCup: 'Personal cup', disposableCup: 'Disposable cup', supplies: 'Supplies', carrier: 'Carrier', straw: 'Straw', couponPoints: 'Coupons & points', noBenefits: 'No coupons or points are available. Discount ₩0', paymentMethod: 'Payment method', card: 'Card', mobilePay: 'Mobile', gifticon: 'Gifticon', splitPayment: 'Split payment', noSplit: 'No split', byItem: 'By item', equalSplit: 'Equal split', peopleCount: 'People', receipt: 'Receipt', paperReceipt: 'Paper', digitalReceipt: 'Digital', noReceipt: 'None', demoOnly: 'Demo only', demoNotice: 'No real payment or store submission will occur.', finalTotal: 'Final total', confirmDemoOrder: 'Confirm demo order', orderComplete: 'Demo order confirmed', orderNotSubmitted: 'No real payment or store submission was made.', orderNumber: 'Demo order number: {number}',
    apiTitle: 'Connect OpenAI API key', apiDescription: 'Enter an API key to chat. It stays only in this page’s memory and is not saved.', apiKeyLabel: 'OpenAI API key', apiPrivacy: 'The key disappears when you refresh or close the page. Do not use it on a shared device.', startWithKey: 'Start with this key', footer: 'Moki Coffee Bar · AI applications team project · Prices and nutrition are fictional for this demo.',
    greeting: 'Hello, I’m Moki. First, please choose the language you prefer. I’ll check the menu data for your tastes and any ingredients you need to avoid. ☕', askMoki: 'Ask Moki', chooseOptions: 'Choose options', photoAlt: '{name} representative image', photoGallery: 'Representative menu images', imageFailed: 'Could not load the photo', imageDescription: 'AI-staged representative image from the Excel photo menu', imageNote: 'Appearance can vary with temperature, size, and options.', thinking: 'Checking the menu data…', requestFailed: 'Could not process the request.', answerFailed: 'Could not load an answer.', checkConnection: 'Please check the connection.', responseFormat: 'Please check the server response.', keyRequired: 'Please enter an API key.',
    staffNeeded: 'Staff verification is required for this purchase. I’ll call a staff member.', staffDone: 'Age verification is complete. Increasing the alcohol type or quantity requires another check.', alcoholInCart: 'Alcohol is in the cart, so staff verification is required.', staffRetry: 'Retry verified request', codeFourDigits: 'Enter the 4-digit staff code.', staffProcessing: 'Processing staff verification…', alcoholCancelled: 'The alcohol purchase was cancelled. You can continue with other menu items.', edit: 'Edit', remove: 'Remove', decrease: 'Decrease quantity', increase: 'Increase quantity', cartUpdated: 'Cart updated.', addedToCart: '{name} was added to your cart.', selectOptionsFor: 'Choose {name} options', cartActionFailed: 'Could not update the cart.',
    suggestions: 'Optional suggestions', sizeUp: 'Change to {size} (+{price})', addShot: 'Add 1 shot (+{price})', pairing: 'Pair with {name}? ({price})', accept: 'Apply', skip: 'Skip', suggestionAccepted: 'Applied.', suggestionSkipped: 'Keeping the default.', pairingNext: 'Now review the paired item’s options.', cartEmptyCheckout: 'Add a menu item before reviewing your order.', retryCheckout: 'Could not confirm the demo order. Check your connection and selections, then press the button again.', confirming: 'Confirming…', tableChanging: 'Changing the table…', tableChangeFailed: 'Could not change the table.', resetDone: 'Chat and cart reset.',
  },
  zh: {
    batchProgress: '复合订单 {current}/{total}·正在确认选项', batchPending: '发送新消息前，请按顺序确认或取消剩余选项。', cancelBatch: '取消剩余选项', batchCancelled: '已取消剩余的菜单选项确认。',
    staffCodeChatPrompt: '请前往员工确认区域，由员工输入 4 位代码。',
    benefitCheckResult: '会员·优惠券·积分查询结果', noLinkedBenefits: '没有已连接的优惠，折扣为 0 韩元。', beforeDiscount: '折扣前金额', discountAmount: '折扣', afterDiscount: '折扣后金额', demoPaymentComplete: '演示支付完成', paidAmount: '最终演示金额', benefitApplied: '会员·优惠适用', benefitNotApplied: '无已连接优惠', orderNumberLabel: '订单号',
    receiptCallout: '{number} 号顾客，请稍候！', receiptItems: '订单商品', subtotal: '小计', demoReceiptLabel: '演示支付收据',
    documentTitle: 'Moki 咖啡吧', skipToChat: '跳转到对话', brandHome: 'Moki 咖啡吧首页', brandTagline: '在韩屋里慢慢选一杯', checkingContent: '正在检查内容', connectedDemo: '数据已连接·演示模式', connectedAI: '数据与 AI 已就绪', keyNeeded: '数据已连接·需要 API 密钥', connectionError: '请检查连接', easyView: '无障碍视图', apiKey: 'API 密钥', apiKeyChange: '更改 OpenAI API 密钥', apiKeyEnter: '输入 OpenAI API 密钥',
    heroTitle: '慢慢挑选<br>今日的一杯。', heroDescription: 'Moki 会根据菜单数据帮您推荐、选项和确认过敏原。', talkToMoki: '与 Moki 对话', heroAlt: '拿着咖啡问候的 Moki', photoMenu: '图片菜单', photoMenuNote: '数据文件中的 33 张代表图片', menuCategories: '菜单分类', menuLoading: '正在准备菜单。', conversationTitle: '与 Moki 对话', listenAnswer: '听回答', messageLabel: '发给 Moki 的消息', messagePlaceholder: '例：请推荐低酸、香浓的咖啡', send: '发送', chatHelper: '价格和选项会与服务器菜单数据再次核对。',
    settings: '使用设置', tableNumber: '桌号', tableOption: '{n} 号桌', staffCodeLabel: '购酒员工确认码', staffCodePlaceholder: '请输入 4 位代码', staffVerify: '员工确认', cancelAlcohol: '取消购酒', reset: '重置对话和购物车', orderDetails: '订单', emptyCart: '购物车还是空的。', total: '合计', reviewOrder: '检查订单', additionalOrder: '继续加单', additionalOrderStarted: '之前的订单仍已确认。请在新购物车中添加同桌的加单商品。', sourcesTitle: '回答参考', sourcesInitial: '开始对话后将显示使用的菜单与指南。', sourcesEmpty: '本次回答不需要其他菜单资料。',
    close: '关闭', easyViewTitle: '无障碍视图', easyViewDescription: '可放大文字和按钮，并提高颜色对比度。', largeText: '大字体', largeTextHelp: '放大整个页面的文字', highContrast: '高对比度', highContrastHelp: '让文字和背景更清晰', largeTargets: '大按钮', largeTargetsHelp: '扩大可点击区域', enableEasyView: '全部开启', resetView: '默认视图', done: '完成', chooseOnce: '一次选定', temperatureSize: '温度·尺寸', quantity: '数量', optionGuidance: '保留默认值即可跳过修改。请在本页一次确认。', expectedAmount: '预计金额', cancel: '取消', addToCart: '加入购物车', saveChanges: '保存更改', optionsTitle: '选项', allergens: '过敏原', noAllergens: '无已标注的过敏信息', defaultChoice: '默认', optionSelectTitle: '选择 {name} 的选项',
    checkoutTitle: '一次检查订单', serviceMode: '用餐方式', dineIn: '堂食', takeout: '外带', cupChoice: '杯子', storeCup: '店内杯', personalCup: '自带杯', disposableCup: '一次性杯', supplies: '所需用品', carrier: '杯托', straw: '吸管', couponPoints: '优惠券·积分', noBenefits: '暂无可用优惠券或积分。优惠 0 韩元', paymentMethod: '支付方式', card: '卡', mobilePay: '移动支付', gifticon: '礼品券', splitPayment: '分开支付', noSplit: '不分开', byItem: '按商品', equalSplit: '平均分', peopleCount: '人数', receipt: '收据', paperReceipt: '纸质', digitalReceipt: '电子', noReceipt: '不需要', demoOnly: '仅供演示', demoNotice: '不会发生真实支付或提交到门店。', finalTotal: '最终金额', confirmDemoOrder: '确认演示订单', orderComplete: '演示订单已确认', orderNotSubmitted: '未进行真实支付或门店提交。', orderNumber: '演示订单号：{number}',
    apiTitle: '连接 OpenAI API 密钥', apiDescription: '输入 API 密钥后即可对话。密钥仅保留在当前页面内存中，不会保存。', apiKeyLabel: 'OpenAI API 密钥', apiPrivacy: '刷新或关闭页面后密钥会消失。请勿在公用设备上使用。', startWithKey: '使用此密钥开始', footer: 'Moki 咖啡吧·AI 应用团队项目·价格和营养信息为演示用虚构设定。',
    greeting: '您好，我是 Moki。请先选择方便的语言。我会根据菜单数据确认您的喜好和需避免的食材。☕', askMoki: '问 Moki', chooseOptions: '选择选项', photoAlt: '{name} 代表图片', photoGallery: '菜单代表图片', imageFailed: '无法加载图片', imageDescription: '来自 Excel 图片菜单的 AI 演绎代表图', imageNote: '实物可能因温度、尺寸和选项而不同。', thinking: '正在检查菜单数据…', requestFailed: '无法处理请求。', answerFailed: '无法加载回答。', checkConnection: '请检查连接。', responseFormat: '请检查服务器响应。', keyRequired: '请输入 API 密钥。',
    staffNeeded: '此购买需要员工确认。我来呼叫员工。', staffDone: '年龄确认已完成。增加酒类或数量时需再次确认。', alcoholInCart: '购物车中有酒类，需要员工确认。', staffRetry: '重试已验证请求', codeFourDigits: '请输入 4 位员工代码。', staffProcessing: '正在处理员工确认…', alcoholCancelled: '已取消酒类购买。您可以继续选择其他商品。', edit: '编辑', remove: '删除', decrease: '减少数量', increase: '增加数量', cartUpdated: '购物车已更新。', addedToCart: '已将 {name} 加入购物车。', selectOptionsFor: '选择 {name} 的选项', cartActionFailed: '无法更新购物车。', suggestions: '可选建议', sizeUp: '更换为 {size}（+{price}）', addShot: '加 1 份浓缩（+{price}）', pairing: '搭配 {name}？（{price}）', accept: '应用', skip: '跳过', suggestionAccepted: '已应用。', suggestionSkipped: '保留默认选择。', pairingNext: '请继续确认搭配商品的选项。', cartEmptyCheckout: '请先将商品加入购物车。', retryCheckout: '无法确认演示订单。检查连接和选项后请再次点击。', confirming: '正在确认…', tableChanging: '正在更改桌号…', tableChangeFailed: '无法更改桌号。', resetDone: '已重置对话和购物车。',
  },
  ja: {
    batchProgress: '複合注文 {current}/{total}・オプション確認中', batchPending: '新しい送信の前に、残りを順番に確認するか取り消してください。', cancelBatch: '残りのオプションを取消', batchCancelled: '残りのメニューオプション確認を取り消しました。',
    staffCodeChatPrompt: 'スタッフ確認欄へ移動し、スタッフが 4 桁のコードを入力してください。',
    benefitCheckResult: 'メンバーシップ・クーポン・ポイント確認結果', noLinkedBenefits: '連携済みの特典はなく、割引は 0 ウォンです。', beforeDiscount: '割引前金額', discountAmount: '割引', afterDiscount: '割引後金額', demoPaymentComplete: 'デモ決済完了', paidAmount: '最終デモ金額', benefitApplied: 'メンバーシップ・特典', benefitNotApplied: '連携済み特典なし', orderNumberLabel: '注文番号',
    receiptCallout: '注文番号 {number} 番のお客様、少々お待ちください！', receiptItems: '注文メニュー', subtotal: '小計', demoReceiptLabel: 'デモ決済レシート',
    documentTitle: 'モキ・コーヒーバー', skipToChat: '会話へ移動', brandHome: 'モキ・コーヒーバーのホーム', brandTagline: '韓屋でゆっくり選ぶ一杯', checkingContent: 'コンテンツを確認中', connectedDemo: 'データ接続済み・デモモード', connectedAI: 'データ・AI 準備完了', keyNeeded: 'データ接続済み・API キーが必要', connectionError: '接続をご確認ください', easyView: 'やさしい表示', apiKey: 'API キー', apiKeyChange: 'OpenAI API キーを変更', apiKeyEnter: 'OpenAI API キーを入力',
    heroTitle: '今日の一杯を<br>ゆっくり選んでください。', heroDescription: 'モキがメニューデータをもとに、おすすめ・オプション・アレルギー確認をお手伝いします。', talkToMoki: 'モキと話す', heroAlt: 'コーヒーを持って挨拶するモキ', photoMenu: '写真メニュー', photoMenuNote: 'データファイル内の代表画像 33 枚', menuCategories: 'メニュー分類', menuLoading: 'メニューを準備中です。', conversationTitle: 'モキと話す', listenAnswer: '回答を聞く', messageLabel: 'モキへのメッセージ', messagePlaceholder: '例：酸味が少なく香ばしいコーヒーをすすめて', send: '送信', chatHelper: '価格とオプションはサーバーのメニューデータと再確認します。',
    settings: '利用設定', tableNumber: 'テーブル番号', tableOption: 'テーブル {n}', staffCodeLabel: '酒類購入のスタッフ確認コード', staffCodePlaceholder: '4 桁のコードを入力', staffVerify: 'スタッフ確認', cancelAlcohol: '酒類購入を取り消す', reset: '会話とカートをリセット', orderDetails: '注文内容', emptyCart: 'カートはまだ空です。', total: '合計', reviewOrder: '注文を確認', additionalOrder: '追加注文する', additionalOrderStarted: '前の注文は確定済みのままです。同じテーブルの追加注文を新しいカートに入れてください。', sourcesTitle: '回答の参考情報', sourcesInitial: '会話を始めるとメニューとガイド資料が表示されます。', sourcesEmpty: 'この回答には別のメニュー資料は必要ありませんでした。',
    close: '閉じる', easyViewTitle: 'やさしい表示', easyViewDescription: '文字やボタンを大きくし、色のコントラストを高められます。', largeText: '大きな文字', largeTextHelp: 'ページ全体の文字を拡大', highContrast: '高コントラスト', highContrastHelp: '文字と背景をより鮮明に', largeTargets: '大きなボタン', largeTargetsHelp: 'タップ領域を拡大', enableEasyView: 'すべてオン', resetView: '標準表示', done: '完了', chooseOnce: '一度に選択', temperatureSize: '温度・サイズ', quantity: '数量', optionGuidance: '変更しない場合は初期値のままです。この画面で一度にご確認ください。', expectedAmount: '予想金額', cancel: 'キャンセル', addToCart: 'カートに入れる', saveChanges: '変更を保存', optionsTitle: 'オプション', allergens: 'アレルゲン', noAllergens: '記載されたアレルギー情報なし', defaultChoice: '標準', optionSelectTitle: '{name} のオプション',
    checkoutTitle: '注文を一度に確認', serviceMode: '利用方法', dineIn: '店内', takeout: 'テイクアウト', cupChoice: 'カップ', storeCup: '店内用カップ', personalCup: 'マイカップ', disposableCup: '使い捨てカップ', supplies: '必要な備品', carrier: 'キャリア', straw: 'ストロー', couponPoints: 'クーポン・ポイント', noBenefits: '利用可能なクーポンやポイントはありません。割引 0 ウォン', paymentMethod: '支払い方法', card: 'カード', mobilePay: 'モバイル', gifticon: 'ギフトコン', splitPayment: '分割支払い', noSplit: '分けない', byItem: '商品別', equalSplit: '均等分割', peopleCount: '人数', receipt: 'レシート', paperReceipt: '紙', digitalReceipt: 'デジタル', noReceipt: '不要', demoOnly: 'デモ専用', demoNotice: '実際の決済や店舗への送信は行われません。', finalTotal: '最終金額', confirmDemoOrder: 'デモ注文を確定', orderComplete: 'デモ注文を確定しました', orderNotSubmitted: '実際の決済や店舗送信は行われていません。', orderNumber: 'デモ注文番号: {number}',
    apiTitle: 'OpenAI API キーを接続', apiDescription: '会話のため API キーを入力してください。キーはこのページのメモリにだけ保持され、保存されません。', apiKeyLabel: 'OpenAI API キー', apiPrivacy: 'ページを更新または閉じるとキーは消えます。共用端末では使用しないでください。', startWithKey: 'このキーで開始', footer: 'モキ・コーヒーバー・AI 応用チームプロジェクト・価格と栄養情報はデモ用の架空設定です。',
    greeting: 'こんにちは、モキです。まず使いやすい言語を選んでください。お好みや避けたい材料をメニューデータで確認します。☕', askMoki: 'モキに聞く', chooseOptions: 'オプションを選ぶ', photoAlt: '{name} の代表画像', photoGallery: 'メニュー代表画像', imageFailed: '画像を読み込めませんでした', imageDescription: 'Excel 写真メニューの AI 演出代表画像', imageNote: '温度・サイズ・オプションにより見た目が異なる場合があります。', thinking: 'メニューデータを確認中…', requestFailed: 'リクエストを処理できませんでした。', answerFailed: '回答を読み込めませんでした。', checkConnection: '接続をご確認ください。', responseFormat: 'サーバー応答をご確認ください。', keyRequired: 'API キーを入力してください。',
    staffNeeded: 'この購入にはスタッフ確認が必要です。スタッフをお呼びします。', staffDone: '年齢確認が完了しました。酒類の種類や数量を増やす場合は再確認します。', alcoholInCart: 'カートに酒類があるためスタッフ確認が必要です。', staffRetry: '確認済みリクエストを再試行', codeFourDigits: '4 桁のスタッフコードを入力してください。', staffProcessing: 'スタッフ確認を処理中…', alcoholCancelled: '酒類の購入を取り消しました。ほかのメニューは続けて選べます。', edit: '編集', remove: '削除', decrease: '数量を減らす', increase: '数量を増やす', cartUpdated: 'カートを更新しました。', addedToCart: '{name} をカートに入れました。', selectOptionsFor: '{name} のオプションを選ぶ', cartActionFailed: 'カートを更新できませんでした。', suggestions: '任意のおすすめ', sizeUp: '{size} に変更（+{price}）', addShot: 'ショット 1 杯追加（+{price}）', pairing: '{name} も一緒に？（{price}）', accept: '適用', skip: 'スキップ', suggestionAccepted: '適用しました。', suggestionSkipped: '標準のままにします。', pairingNext: '続けてペアリング商品のオプションをご確認ください。', cartEmptyCheckout: '注文する商品を先にカートに入れてください。', retryCheckout: 'デモ注文を確定できませんでした。接続と選択を確認し、もう一度ボタンを押してください。', confirming: '確定中…', tableChanging: 'テーブルを変更中…', tableChangeFailed: 'テーブルを変更できませんでした。', resetDone: '会話とカートをリセットしました。',
  },
};

const STAFF_CALL_I18N = {
  ko: {
    staffCall: '직원 호출', staffCallActive: '직원 호출됨', staffCallTitle: '직원 호출',
    staffCallDescription: '메뉴나 이용에 도움이 필요하신가요?', staffCallDemoNotice: '이 화면에서는 실제 직원에게 호출이 전달되지 않습니다.',
    requestStaffCall: '직원 호출하기', staffCallRequestedTitle: '직원 호출을 표시했어요',
    staffCallRequestedDescription: '현재 테이블에 직원 호출 상태가 표시됩니다.', cancelStaffCall: '호출 취소', staffCallCancelled: '직원 호출을 취소했어요.',
  },
  en: {
    staffCall: 'Call staff', staffCallActive: 'Staff called', staffCallTitle: 'Call staff',
    staffCallDescription: 'Do you need help with the menu or your visit?', staffCallDemoNotice: 'This demo does not send a real request to staff.',
    requestStaffCall: 'Call staff', staffCallRequestedTitle: 'Staff call displayed',
    staffCallRequestedDescription: 'This table is now showing a staff-call status.', cancelStaffCall: 'Cancel call', staffCallCancelled: 'The staff call was cancelled.',
  },
  zh: {
    staffCall: '呼叫员工', staffCallActive: '已呼叫员工', staffCallTitle: '呼叫员工',
    staffCallDescription: '需要菜单或用餐方面的帮助吗？', staffCallDemoNotice: '此演示画面不会向真实员工发送请求。',
    requestStaffCall: '呼叫员工', staffCallRequestedTitle: '已显示员工呼叫',
    staffCallRequestedDescription: '当前桌位已显示员工呼叫状态。', cancelStaffCall: '取消呼叫', staffCallCancelled: '已取消员工呼叫。',
  },
  ja: {
    staffCall: 'スタッフを呼ぶ', staffCallActive: 'スタッフ呼出中', staffCallTitle: 'スタッフ呼出',
    staffCallDescription: 'メニューやご利用にお手伝いが必要ですか？', staffCallDemoNotice: 'このデモ画面から実際のスタッフに呼出は送信されません。',
    requestStaffCall: 'スタッフを呼ぶ', staffCallRequestedTitle: 'スタッフ呼出を表示しました',
    staffCallRequestedDescription: '現在のテーブルにスタッフ呼出状態が表示されます。', cancelStaffCall: '呼出を取り消す', staffCallCancelled: 'スタッフ呼出を取り消しました。',
  },
};
Object.entries(STAFF_CALL_I18N).forEach(([locale, messages]) => Object.assign(I18N[locale], messages));

const state = {
  locale: 'ko', localeChosen: false, largeText: false, highContrast: false, largeTargets: false,
  history: [], cart: [], orderNo: null, stateToken: null, cartStatus: null,
  staffChecked: false, staffCallRequested: false, tableId: 5, staffVerificationRequired: false,
  staffVerificationReason: null, staffChallenge: null, staffAuthorization: null,
  pendingStaffRequest: null, pendingCartRollback: null,
  sources: [], menu: [], categories: [], category: '커피',
  quickReplies: [], menuActions: [], busy: false, contentReady: false,
  serverAIReady: false, mockMode: false, optionItem: null, optionEditIndex: null,
  optionPreset: null, deferredItems: [], deferredBatch: null,
  pairingChoice: null, pairingTrail: [], lastCheckout: null,
};
let openAIAPIKey = '';
let apiModalTimer = null;

function tr(key, vars = {}) {
  let value = (I18N[state.locale] && I18N[state.locale][key]) || I18N.ko[key] || key;
  Object.entries(vars).forEach(([name, replacement]) => { value = value.replaceAll(`{${name}}`, String(replacement)); });
  return value;
}

function won(value) {
  return new Intl.NumberFormat(state.locale === 'ko' ? 'ko-KR' : state.locale === 'zh' ? 'zh-CN' : state.locale === 'ja' ? 'ja-JP' : 'en-US', {
    style: 'currency', currency: 'KRW', maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

function announce(message) {
  const live = $('#appStatus');
  live.textContent = '';
  requestAnimationFrame(() => { live.textContent = String(message || ''); });
}

function canonicalImage(menuId) {
  const id = String(menuId || '').toUpperCase();
  return /^M\d{2}$/.test(id) ? `/assets/menu/${id}.jpg` : '';
}

function syncModalState() {
  document.body.classList.toggle('modal-open', $$('dialog[open]').length > 0);
}

function openDialog(dialog) {
  if (!dialog || dialog.open) return;
  dialog.showModal();
  syncModalState();
}

function closeDialog(dialog) {
  if (dialog && dialog.open) dialog.close();
  syncModalState();
}

function renderStaffCallState() {
  const active = state.staffCallRequested;
  const button = $('#staffCallButton');
  button.textContent = tr(active ? 'staffCallActive' : 'staffCall');
  button.classList.toggle('active', active);
  button.setAttribute('aria-pressed', String(active));
  $('#staffCallPrompt').hidden = active;
  $('#staffCallSuccess').hidden = !active;
}

function openStaffCallDialog() {
  renderStaffCallState();
  openDialog($('#staffCallModal'));
}

function requestStaffCall() {
  state.staffCallRequested = true;
  renderStaffCallState(); saveState();
  announce(tr('staffCallRequestedTitle'));
}

function cancelStaffCall() {
  state.staffCallRequested = false;
  renderStaffCallState(); saveState();
  closeDialog($('#staffCallModal'));
  announce(tr('staffCallCancelled'));
  $('#staffCallButton').focus();
}

function resetOptionDialogState() {
  state.optionItem = null;
  state.optionEditIndex = null;
  state.optionPreset = null;
  state.pairingChoice = null;
  state.pairingTrail = [];
}

function closeOptionDialog() {
  closeDialog($('#optionModal'));
  resetOptionDialogState();
}

function errorMessage(detail, fallback) {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) return detail.map((item) => item && item.msg ? item.msg : String(item)).join(' · ');
  return fallback || tr('requestFailed');
}

async function responsePayload(response) {
  const text = await response.text();
  if (!text) return {};
  try { return JSON.parse(text); }
  catch (_) { return { detail: response.ok ? '' : tr('responseFormat') }; }
}

function loadPreferences() {
  try {
    const saved = JSON.parse(localStorage.getItem(PREFERENCE_KEY) || '{}');
    state.locale = LOCALES.includes(saved.locale) ? saved.locale : 'ko';
    state.localeChosen = Boolean(saved.localeChosen && LOCALES.includes(saved.locale));
    state.largeText = Boolean(saved.largeText);
    state.highContrast = Boolean(saved.highContrast);
    state.largeTargets = Boolean(saved.largeTargets);
  } catch (_) { localStorage.removeItem(PREFERENCE_KEY); }
}

function savePreferences() {
  localStorage.setItem(PREFERENCE_KEY, JSON.stringify({
    locale: state.locale, localeChosen: state.localeChosen,
    largeText: state.largeText, highContrast: state.highContrast,
    largeTargets: state.largeTargets,
  }));
}

function applyAccessibility() {
  document.documentElement.dataset.textSize = state.largeText ? 'large' : 'normal';
  document.documentElement.dataset.contrast = state.highContrast ? 'high' : 'normal';
  document.documentElement.dataset.touchSize = state.largeTargets ? 'large' : 'normal';
  $('#largeTextToggle').checked = state.largeText;
  $('#highContrastToggle').checked = state.highContrast;
  $('#largeTargetsToggle').checked = state.largeTargets;
  $('#easyViewButton').classList.toggle('active', state.largeText || state.highContrast || state.largeTargets);
}

function translateStaticPage() {
  document.documentElement.lang = state.locale === 'zh' ? 'zh-Hans' : state.locale;
  document.title = tr('documentTitle');
  $$('[data-i18n]').forEach((element) => { element.textContent = tr(element.dataset.i18n); });
  $$('[data-i18n-html]').forEach((element) => { element.innerHTML = tr(element.dataset.i18nHtml); });
  $$('[data-i18n-placeholder]').forEach((element) => { element.placeholder = tr(element.dataset.i18nPlaceholder); });
  $$('[data-i18n-aria]').forEach((element) => { element.setAttribute('aria-label', tr(element.dataset.i18nAria)); });
  $$('[data-i18n-alt]').forEach((element) => { element.alt = tr(element.dataset.i18nAlt); });
  $('#currentLanguageLabel').textContent = LANGUAGE_LABELS[state.locale];
  $('#languageClose').hidden = !state.localeChosen;
  renderStaffCallState();
  refreshConnectionStatus();
}

function setLocale(locale, { close = true, announceChange = true } = {}) {
  if (!LOCALES.includes(locale)) return;
  state.locale = locale;
  state.localeChosen = true;
  savePreferences();
  translateStaticPage();
  renderTableOptions();
  renderHistory();
  renderCategories();
  renderMenu();
  renderCart();
  renderSources();
  renderStaffStatus();
  renderQuickReplies();
  if ($('#optionModal').open && state.optionItem) renderOptionDialog();
  if ($('#checkoutModal').open) {
    if (!$('#orderSuccess').hidden && state.lastCheckout) renderCheckoutReceipt(state.lastCheckout);
    else { renderCheckoutReview(); renderCupChoices(); }
  }
  if (close) closeDialog($('#languageModal'));
  if (announceChange) announce(`${LANGUAGE_LABELS[locale]} · ${tr('done')}`);
  scheduleAPIKeyModal();
}

function detectInputLocale(message) {
  const text = String(message || '').trim();
  if (!text) return null;
  const hangul = (text.match(/[\uac00-\ud7a3]/g) || []).length;
  const kana = (text.match(/[\u3040-\u30ff]/g) || []).length;
  const han = (text.match(/[\u3400-\u9fff]/g) || []).length;
  const latinWords = text.match(/[A-Za-z]+(?:'[A-Za-z]+)?/g) || [];

  // A single foreign menu name should not unexpectedly change the whole UI.
  if (hangul && (hangul >= 8 || /\s/.test(text) || /안녕|주세요|추천|어떤|할까|해줘|해주세요/.test(text))) return 'ko';
  if (kana >= 2) return 'ja';
  if (han >= 4 || (han >= 2 && state.locale !== 'ja' && /你好|请|我要|推荐|哪个|可以/.test(text))) return 'zh';
  if (latinWords.length >= 3 || /^(?:hello|hi|please|can|could|recommend|show|what|which|order|add|remove|change|checkout)\b/i.test(text)) return 'en';
  return null;
}

function applyDetectedLocale(message) {
  const locale = detectInputLocale(message);
  if (!locale || locale === state.locale) return;
  setLocale(locale, { close: false, announceChange: false });
  announce(LANGUAGE_DETECTED_MESSAGES[locale]);
}

function isAdditionalOrderRequest(message) {
  const text = String(message || '').trim().toLowerCase();
  if (!text) return false;
  if (/(?:how\s+to.{0,16}(?:another|additional)\s+order|(?:추가\s*주문|another\s+order|additional\s+order|加单|追加订单|追加注文).{0,12}(?:가능|어떻게|할\s*수|있나|있어\s*\?|possible|how\s+to|可以吗|怎么|できますか|方法))/i.test(text)) return false;
  return /(?:추가\s*주문(?:하고\s*싶|할게|할래|해\s*줘|해\s*주세요|시작|하려고)?|더\s*(?:주문|시키|담)(?:하고\s*싶|할게|할래|을게|어\s*줘)?|\b(?:another|additional|new)\s+order\b|\border\s+more\b|加单|追加订单|再点|追加注文|もう.{0,8}注文)/i.test(text);
}

function setAccessibility(name, value) {
  state[name] = Boolean(value);
  applyAccessibility();
  savePreferences();
}

function setConnection(kind, text) {
  const element = $('#connectionStatus');
  element.className = `connection ${kind || ''}`;
  $('span', element).textContent = text;
}

function refreshConnectionStatus() {
  const keyButton = $('#apiKeyButton');
  keyButton.classList.toggle('connected', Boolean(openAIAPIKey));
  keyButton.setAttribute('aria-label', openAIAPIKey ? tr('apiKeyChange') : tr('apiKeyEnter'));
  if (!state.contentReady) return;
  if (state.mockMode) setConnection('', tr('connectedDemo'));
  else if (state.serverAIReady || openAIAPIKey) setConnection('ready', tr('connectedAI'));
  else setConnection('', tr('keyNeeded'));
}

function openAPIKeyModal() {
  const input = $('#apiKeyInput');
  input.value = '';
  $('#apiKeyError').textContent = '';
  $('#apiKeyCancel').hidden = !(openAIAPIKey || state.serverAIReady || state.mockMode);
  openDialog($('#apiKeyModal'));
  requestAnimationFrame(() => input.focus());
}

function closeAPIKeyModal() {
  $('#apiKeyInput').value = '';
  $('#apiKeyError').textContent = '';
  closeDialog($('#apiKeyModal'));
}

function scheduleAPIKeyModal() {
  clearTimeout(apiModalTimer);
  if (!state.localeChosen || openAIAPIKey || state.serverAIReady || state.mockMode) return;
  apiModalTimer = setTimeout(() => {
    if (!$$('dialog[open]').length && !openAIAPIKey && !state.serverAIReady && !state.mockMode) openAPIKeyModal();
  }, API_MODAL_DELAY_MS);
}

function submitAPIKey(event) {
  event.preventDefault();
  const input = $('#apiKeyInput');
  const candidate = input.value.trim();
  input.value = '';
  if (!candidate) {
    $('#apiKeyError').textContent = tr('keyRequired');
    input.focus();
    return;
  }
  openAIAPIKey = candidate;
  closeAPIKeyModal();
  refreshConnectionStatus();
  if (state.staffAuthorization && state.pendingStaffRequest) void retryPendingStaffRequest();
  else $('#messageInput').focus();
}

function createAvatar() {
  const avatar = document.createElement('img');
  avatar.className = 'avatar'; avatar.src = AVATAR_URL; avatar.alt = 'Moki';
  avatar.onerror = () => {
    const fallback = document.createElement('span');
    fallback.className = 'avatar avatar-fallback'; fallback.role = 'img';
    fallback.ariaLabel = 'Moki'; fallback.textContent = 'Moki'; avatar.replaceWith(fallback);
  };
  return avatar;
}

function normalizeMenuImages(items) {
  const seen = new Set();
  const normalized = [];
  (Array.isArray(items) ? items : []).forEach((item) => {
    if (!item || normalized.length >= 3) return;
    const id = String(item.id || item.menu_id || '').toUpperCase();
    if (!/^M\d{2}$/.test(id) || seen.has(id)) return;
    seen.add(id);
    const menu = state.menu.find((entry) => entry.id === id);
    normalized.push({
      id,
      name: String(menu ? menuDisplayName(menu) : item.name || id).trim().slice(0, 80) || id,
      description: state.locale === 'ko'
        ? String(item.description || (menu && menu.description) || '').trim().slice(0, 180) : '',
      image: canonicalImage(id),
    });
  });
  return normalized;
}

function createMenuImageGallery(items) {
  const images = normalizeMenuImages(items);
  if (!images.length) return null;
  const gallery = document.createElement('div');
  gallery.className = 'message-menu-images'; gallery.role = 'list'; gallery.ariaLabel = tr('photoGallery');
  images.forEach((item) => {
    const card = document.createElement('figure'); card.className = 'message-menu-image-card'; card.role = 'listitem';
    const image = document.createElement('img');
    image.src = item.image; image.alt = tr('photoAlt', { name: item.name });
    image.loading = 'lazy'; image.decoding = 'async'; image.width = 600; image.height = 600;
    image.onerror = () => {
      const fallback = document.createElement('div');
      fallback.className = 'message-menu-image-fallback'; fallback.role = 'img';
      fallback.ariaLabel = tr('imageFailed'); fallback.textContent = tr('imageFailed'); image.replaceWith(fallback);
    };
    const caption = document.createElement('figcaption');
    const name = document.createElement('strong'); name.textContent = item.name;
    const description = document.createElement('span'); description.textContent = item.description || tr('imageDescription');
    const note = document.createElement('small'); note.textContent = tr('imageNote');
    caption.append(name, description, note); card.append(image, caption); gallery.appendChild(card);
  });
  return gallery;
}

function appendMessage(role, content, save = true, menuImages = []) {
  const safeContent = String(content || '');
  const normalizedImages = role === 'assistant' ? normalizeMenuImages(menuImages) : [];
  if (save) {
    const message = { role, content: safeContent };
    if (normalizedImages.length) message.menu_images = normalizedImages;
    state.history.push(message);
  }
  const row = document.createElement('div'); row.className = `message ${role}`;
  if (role === 'assistant') row.appendChild(createAvatar());
  const body = document.createElement('div'); body.className = 'message-body';
  if (role === 'assistant') {
    const speaker = document.createElement('div'); speaker.className = 'speaker'; speaker.textContent = 'Moki'; body.appendChild(speaker);
  }
  const bubble = document.createElement('div'); bubble.className = 'bubble'; bubble.textContent = safeContent; body.appendChild(bubble);
  const gallery = createMenuImageGallery(normalizedImages);
  if (gallery) body.appendChild(gallery);
  row.appendChild(body); $('#messages').appendChild(row);
  $('#messages').scrollTop = $('#messages').scrollHeight;
}

function renderHistory() {
  $('#messages').replaceChildren();
  if (!state.history.length) {
    appendMessage('assistant', tr('greeting'), false);
    return;
  }
  state.history.forEach((message) => appendMessage(message.role, message.content, false, message.menu_images));
}

function renderTableOptions() {
  const select = $('#tableSelect');
  select.replaceChildren();
  for (let table = 1; table <= 12; table += 1) {
    const option = document.createElement('option');
    option.value = table; option.textContent = tr('tableOption', { n: table }); option.selected = table === state.tableId;
    select.appendChild(option);
  }
  $('#tableBadge').textContent = `TABLE ${String(state.tableId).padStart(2, '0')}`;
}

function renderCategories() {
  const tabs = $('#categoryTabs'); tabs.replaceChildren();
  state.categories.forEach((category) => {
    const button = document.createElement('button');
    button.type = 'button'; button.textContent = CATEGORY_LABELS[state.locale][category] || category;
    button.className = category === state.category ? 'active' : '';
    button.setAttribute('aria-pressed', String(category === state.category));
    button.onclick = () => { state.category = category; renderCategories(); renderMenu(); };
    tabs.appendChild(button);
  });
}

function menuDisplayName(item) {
  if (state.locale === 'ko') return item.name;
  if (state.locale === 'en') return item.name_en || item.name;
  return (MENU_NAMES[state.locale] && MENU_NAMES[state.locale][item.id]) || item.name_en || item.name;
}

function menuDetailQuestion(item) {
  const name = menuDisplayName(item);
  return {
    ko: `${name}에 대해 자세히 알려줘`,
    en: `Tell me more about ${name}.`,
    zh: `请详细介绍一下${name}。`,
    ja: `${name}について詳しく教えてください。`,
  }[state.locale];
}

function localizedAllergens(raw) {
  const normalized = String(raw || '').trim();
  if (!normalized) return tr('noAllergens');
  const terms = {
    en: { '레시피상 지정 재료 없음': 'No listed recipe allergen', '우유': 'milk', '대두': 'soy', '밀': 'wheat', '계란': 'egg', '보리': 'barley', '참깨': 'sesame', '아황산류': 'sulfites' },
    zh: { '레시피상 지정 재료 없음': '配方未标注过敏原', '우유': '牛奶', '대두': '大豆', '밀': '小麦', '계란': '鸡蛋', '보리': '大麦', '참깨': '芝麻', '아황산류': '亚硫酸盐' },
    ja: { '레시피상 지정 재료 없음': 'レシピ上の指定アレルゲンなし', '우유': '乳', '대두': '大豆', '밀': '小麦', '계란': '卵', '보리': '大麦', '참깨': 'ごま', '아황산류': '亜硫酸塩' },
  };
  if (state.locale === 'ko') return normalized;
  if (terms[state.locale][normalized]) return terms[state.locale][normalized];
  return normalized.split(',').map((part) => terms[state.locale][part.trim()] || part.trim()).join(', ');
}

function renderMenu() {
  const grid = $('#menuGrid');
  if (!state.menu.length) return;
  grid.replaceChildren();
  state.menu.filter((item) => item.category === state.category).forEach((item) => {
    const displayName = menuDisplayName(item);
    const card = document.createElement('article'); card.className = 'menu-card';
    const image = document.createElement('img'); image.src = canonicalImage(item.id); image.alt = tr('photoAlt', { name: displayName }); image.loading = 'lazy';
    image.onerror = () => { image.classList.add('image-error'); image.alt = tr('imageFailed'); };
    const body = document.createElement('div'); body.className = 'menu-card-body';
    const title = document.createElement('h3'); title.textContent = displayName;
    const subtitle = document.createElement('small'); subtitle.textContent = state.locale === 'ko' ? item.name_en : item.name;
    const price = document.createElement('strong');
    const prices = (item.variants || []).map((variant) => Number(variant.price)).filter(Number.isFinite);
    price.textContent = prices.length ? `${won(Math.min(...prices))}${new Set(prices).size > 1 ? '+' : ''}` : item.price_label;
    const actions = document.createElement('div'); actions.className = 'menu-card-actions';
    const ask = document.createElement('button'); ask.type = 'button'; ask.className = 'menu-ask'; ask.textContent = tr('askMoki');
    ask.onclick = () => { $('#conversation').scrollIntoView({ behavior: 'smooth' }); sendMessage(menuDetailQuestion(item)); };
    const choose = document.createElement('button'); choose.type = 'button'; choose.className = 'menu-choose'; choose.textContent = tr('chooseOptions');
    choose.onclick = () => openOptionDialog(item.id);
    actions.append(ask, choose); body.append(title, subtitle, price, actions); card.append(image, body); grid.appendChild(card);
  });
}

function localizedOptionValue(key, value, fallback = '') {
  const values = {
    bean: {
      B01: ['하우스', 'House', '经典配方', 'ハウス'], B02: ['에티오피아 싱글오리진', 'Ethiopia single origin', '埃塞俄比亚单品', 'エチオピア・シングルオリジン'], B03: ['콜롬비아 디카페인', 'Colombia decaf', '哥伦比亚低因', 'コロンビア・デカフェ'],
    },
    milk: {
      dairy: ['일반 우유', 'Dairy milk', '牛奶', '牛乳'], lowfat: ['저지방 우유', 'Low-fat milk', '低脂牛奶', '低脂肪乳'], oat: ['오트 음료', 'Oat drink', '燕麦奶', 'オーツミルク'], soy: ['두유', 'Soy milk', '豆奶', '豆乳'],
    },
    sweetness: { normal: ['기본', 'Regular', '标准', '標準'], less: ['절반', 'Half sweet', '半糖', '甘さ半分'] },
    ice: { normal: ['기본', 'Regular ice', '正常冰', '通常'], less: ['적게', 'Less ice', '少冰', '氷少なめ'] },
    warming: { room: ['기본', 'As served', '默认', '標準'], warm: ['따뜻하게', 'Warmed', '加热', '温める'] },
  };
  if (key === 'extra_shots') {
    const number = Number(value);
    return number ? ({ ko: `+${number}샷`, en: `+${number} shot${number > 1 ? 's' : ''}`, zh: `+${number} 份浓缩`, ja: `+${number} ショット` }[state.locale]) : tr('defaultChoice');
  }
  const index = { ko: 0, en: 1, zh: 2, ja: 3 }[state.locale];
  return values[key] && values[key][value] ? values[key][value][index] : (fallback || String(value));
}

function optionFieldLabel(key) {
  const labels = {
    bean: { ko: '원두', en: 'Beans', zh: '咖啡豆', ja: 'コーヒー豆' },
    extra_shots: { ko: '추가 샷', en: 'Extra shots', zh: '额外浓缩', ja: '追加ショット' },
    milk: { ko: '우유', en: 'Milk', zh: '奶类', ja: 'ミルク' },
    sweetness: { ko: '당도', en: 'Sweetness', zh: '甜度', ja: '甘さ' },
    ice: { ko: '얼음', en: 'Ice', zh: '冰量', ja: '氷' },
    warming: { ko: '데우기', en: 'Warming', zh: '加热', ja: '温め' },
  };
  return labels[key] ? labels[key][state.locale] : key;
}

function variantLabel(variant) {
  const temp = {
    ko: { HOT: '핫', ICED: '아이스', NA: '' }, en: { HOT: 'Hot', ICED: 'Iced', NA: '' },
    zh: { HOT: '热', ICED: '冰', NA: '' }, ja: { HOT: 'ホット', ICED: 'アイス', NA: '' },
  }[state.locale][variant.temp] || variant.temp;
  const size = variant.size === 'ONE' || variant.size === 'NA' ? '' : variant.size;
  return [temp, size, won(variant.price)].filter(Boolean).join(' · ');
}

function cartOptionText(item) {
  const menu = state.menu.find((entry) => entry.id === item.menu_id);
  const variant = menu && (menu.variants || []).find((entry) => entry.id === item.variant_id);
  const parts = [variant ? variantLabel(variant) : [item.temp, item.size].filter((value) => value && value !== 'NA' && value !== 'ONE').join(' · ')];
  ['bean', 'extra_shots', 'milk', 'sweetness', 'ice', 'warming'].forEach((key) => {
    const value = item[key];
    const isDefault = value == null || value === 0 || ['B01', 'dairy', 'normal', 'room'].includes(value);
    if (!isDefault) parts.push(localizedOptionValue(key, value));
  });
  return parts.filter(Boolean).join(' · ');
}

function cartHasAlcohol() {
  if (state.cartStatus === 'pending_staff_check') return true;
  const alcoholIds = new Set(state.menu.filter((item) => item.is_alcohol || item.category === '주류').map((item) => item.id));
  return state.cart.some((item) => alcoholIds.has(item.menu_id));
}

function menuIsAlcohol(menuId) {
  const menu = state.menu.find((item) => item.id === String(menuId || '').toUpperCase());
  return Boolean(menu && (menu.is_alcohol || menu.category === '주류'));
}

function cartActionNeedsAlcoholApproval(action, fields = {}) {
  const current = Number.isInteger(fields.index) ? state.cart[fields.index] : null;
  if (action === 'add') return Boolean(fields.item && menuIsAlcohol(fields.item.menu_id));
  if (action === 'set_qty') {
    return Boolean(current && menuIsAlcohol(current.menu_id) && Number(fields.quantity) > Number(current.qty));
  }
  if (action === 'replace') {
    return Boolean(fields.item && menuIsAlcohol(fields.item.menu_id) && (!current
      || fields.item.variant_id !== current.variant_id
      || Number(fields.item.qty) > Number(current.qty)));
  }
  return false;
}

function renderCart() {
  const confirmed = Boolean(state.orderNo);
  const wrap = $('#cartItems'); wrap.replaceChildren();
  if (!state.cart.length) {
    const empty = document.createElement('p'); empty.className = 'empty'; empty.textContent = tr('emptyCart'); wrap.appendChild(empty);
  }
  state.cart.forEach((item, index) => {
    const menu = state.menu.find((entry) => entry.id === item.menu_id);
    const nameText = menu ? menuDisplayName(menu) : item.name;
    const line = document.createElement('article'); line.className = 'cart-line';
    const image = document.createElement('img'); image.className = 'cart-thumb'; image.src = canonicalImage(item.menu_id); image.alt = tr('photoAlt', { name: nameText });
    const copy = document.createElement('div'); copy.className = 'cart-line-copy';
    const name = document.createElement('b'); name.textContent = nameText;
    const options = document.createElement('small'); options.textContent = cartOptionText(item);
    const price = document.createElement('div'); price.className = 'cart-line-price'; price.textContent = won(item.subtotal);
    const controls = document.createElement('div'); controls.className = 'cart-controls';
    const minus = document.createElement('button'); minus.type = 'button'; minus.textContent = '−'; minus.ariaLabel = `${nameText}: ${tr('decrease')}`; minus.disabled = confirmed || Number(item.qty) <= 1;
    minus.onclick = () => cartAction('set_qty', { index, quantity: Number(item.qty) - 1 });
    const quantity = document.createElement('span'); quantity.textContent = String(item.qty); quantity.ariaLabel = `${tr('quantity')} ${item.qty}`;
    const plus = document.createElement('button'); plus.type = 'button'; plus.textContent = '+'; plus.ariaLabel = `${nameText}: ${tr('increase')}`; plus.disabled = confirmed || Number(item.qty) >= 10;
    plus.onclick = () => cartAction('set_qty', { index, quantity: Number(item.qty) + 1 });
    const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'cart-text-button'; edit.textContent = tr('edit'); edit.disabled = confirmed; edit.onclick = () => openOptionDialog(item.menu_id, index);
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'cart-text-button danger'; remove.textContent = tr('remove'); remove.disabled = confirmed; remove.ariaLabel = `${nameText}: ${tr('remove')}`; remove.onclick = () => cartAction('remove', { index });
    controls.append(minus, quantity, plus, edit, remove); copy.append(name, options, price, controls); line.append(image, copy); wrap.appendChild(line);
  });
  const total = state.cart.reduce((sum, item) => sum + Number(item.subtotal || 0), 0);
  $('#cartTotal').textContent = won(total);
  $('#confirmButton').disabled = !state.cart.length;
  $('#additionalOrderCartButton').hidden = !confirmed;
  if ($('#checkoutModal').open) {
    if (!$('#orderSuccess').hidden && state.lastCheckout) renderCheckoutReceipt(state.lastCheckout);
    else renderCheckoutReview();
  }
}

function renderStaffStatus(message = '', focus = false) {
  const verification = $('#staffVerification');
  const hasAlcohol = cartHasAlcohol();
  const visible = state.staffVerificationRequired || hasAlcohol;
  const needsCode = state.staffVerificationRequired || (hasAlcohol && !state.staffChecked);
  const codeInput = $('#staffCodeInput');
  $('label', verification).hidden = !needsCode;
  codeInput.hidden = !needsCode;
  $('#staffVerifyButton').hidden = !needsCode;
  $('#staffCancelButton').hidden = !needsCode;
  verification.hidden = !visible;
  if (!visible) { codeInput.value = ''; $('#staffStatus').textContent = ''; return; }
  const status = $('#staffStatus');
  status.className = `setting-note${state.staffChecked && !state.staffVerificationRequired ? ' ready' : ''}`;
  status.textContent = message || (state.staffVerificationRequired ? tr('staffNeeded') : state.staffChecked ? tr('staffDone') : tr('alcoholInCart'));
  if (focus && needsCode) requestAnimationFrame(() => codeInput.focus());
}

function revealStaffVerification(message = '') {
  renderStaffStatus(message, true);
  openDialog($('#staffCodeModal'));
  const verification = $('#staffVerification');
  verification.classList.remove('attention');
  // Restart the visual cue even when two purchase actions are attempted in a row.
  void verification.offsetWidth;
  verification.classList.add('attention');
  requestAnimationFrame(() => {
    verification.scrollIntoView({ behavior: 'smooth', block: 'center' });
    if (!$('#staffCodeInput').hidden) $('#staffCodeInput').focus({ preventScroll: true });
  });
  setTimeout(() => verification.classList.remove('attention'), 4200);
}

function renderSources() {
  const wrap = $('#sources'); wrap.replaceChildren();
  if (!state.sources.length) {
    const empty = document.createElement('p'); empty.className = 'empty'; empty.textContent = state.history.length ? tr('sourcesEmpty') : tr('sourcesInitial'); wrap.appendChild(empty); return;
  }
  state.sources.forEach((source) => {
    const row = document.createElement('div'); row.className = 'source-chip';
    const sourceLabels = {
      '메뉴': { ko: '메뉴', en: 'Menu', zh: '菜单', ja: 'メニュー' },
      '매장 안내': { ko: '매장 안내', en: 'Guide', zh: '门店指南', ja: '店舗ガイド' },
      '정책': { ko: '정책', en: 'Policy', zh: '规定', ja: 'ポリシー' },
      '원두': { ko: '원두', en: 'Beans', zh: '咖啡豆', ja: 'コーヒー豆' },
      '용어 안내': { ko: '용어 안내', en: 'Glossary', zh: '术语说明', ja: '用語ガイド' },
      '안내': { ko: '안내', en: 'Guide', zh: '指南', ja: 'ガイド' },
    };
    const label = document.createElement('span'); label.textContent = sourceLabels[source.label]?.[state.locale] || source.label || '✓';
    const menu = state.menu.find((entry) => entry.id === source.id);
    row.append(label, document.createTextNode(menu ? menuDisplayName(menu) : (source.name || source.id || ''))); wrap.appendChild(row);
  });
}

function normalizeMenuActions(actions) {
  const ids = [];
  (Array.isArray(actions) ? actions : []).forEach((action) => {
    const id = String(typeof action === 'string' ? action : (action && (action.menu_id || action.id)) || '').toUpperCase();
    if (/^M\d{2}$/.test(id) && !ids.includes(id) && state.menu.some((item) => item.id === id)) ids.push(id);
  });
  return ids.slice(0, 4);
}

function renderLanguageChoices(container) {
  LOCALES.forEach((locale) => {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'language-chip';
    button.textContent = LANGUAGE_LABELS[locale]; button.ariaPressed = String(state.locale === locale);
    button.onclick = () => setLocale(locale); container.appendChild(button);
  });
}

function proposalFingerprint(proposal) {
  return ['menu_id', 'variant_id', 'qty', 'bean', 'extra_shots', 'milk', 'sweetness', 'ice', 'warming']
    .map((key) => String(proposal && proposal[key] != null ? proposal[key] : '')).join('|');
}

function proposalKey(proposal) {
  const proposalId = String(proposal && proposal.proposal_id || '').trim();
  return proposalId ? `id:${proposalId}` : `values:${proposalFingerprint(proposal)}`;
}

function normalizeDeferredItems(items) {
  return (Array.isArray(items) ? items : []).map((raw, index) => {
    if (!raw || typeof raw !== 'object') return null;
    const proposal = {
      ...raw,
      menu_id: String(raw.menu_id || '').toUpperCase(),
      variant_id: String(raw.variant_id || ''),
      qty: Math.max(1, Math.min(10, Number(raw.qty || 1))),
    };
    if (!/^M\d{2}$/.test(proposal.menu_id) || !Number.isFinite(proposal.qty)) return null;
    const suppliedId = String(raw.proposal_id || '').trim().slice(0, 120);
    proposal.proposal_id = suppliedId || `local-${index}-${proposalFingerprint(proposal)}`;
    if (!state.menu.length) return proposal;
    const menu = state.menu.find((entry) => entry.id === proposal.menu_id);
    return menu && (menu.variants || []).some((variant) => variant.id === proposal.variant_id) ? proposal : null;
  }).filter(Boolean);
}

function normalizeDeferredBatch(batch, items = state.deferredItems) {
  if (!items.length) return null;
  const savedCompleted = Number(batch && batch.completed);
  const savedTotal = Number(batch && batch.total);
  const completed = Number.isFinite(savedCompleted) ? Math.max(0, Math.floor(savedCompleted)) : 0;
  const total = Math.max(
    completed + items.length,
    Number.isFinite(savedTotal) ? Math.floor(savedTotal) : 0,
  );
  const menuIds = [...new Set([
    ...(Array.isArray(batch && batch.menuIds) ? batch.menuIds : []),
    ...items.map((proposal) => proposal.menu_id),
  ].filter((id) => /^M\d{2}$/.test(String(id))))];
  return {
    id: String(batch && batch.id || `batch-${Date.now()}`).slice(0, 120),
    total,
    completed: Math.min(completed, Math.max(0, total - items.length)),
    menuIds,
  };
}

function setResponseChoices(replies, menuActions, deferredItems) {
  const deferred = normalizeDeferredItems(deferredItems);
  if (deferred.length) {
    state.deferredItems = deferred;
    state.deferredBatch = normalizeDeferredBatch({
      id: `batch-${Date.now()}`,
      total: deferred.length,
      completed: 0,
      menuIds: deferred.map((proposal) => proposal.menu_id),
    }, deferred);
    // A structured order batch is the only actionable choice. Keeping generic
    // quick replies here lets a second chat response overwrite the remaining queue.
    state.quickReplies = [];
    state.menuActions = [];
  } else {
    state.deferredItems = [];
    state.deferredBatch = null;
    state.quickReplies = Array.isArray(replies) ? replies : [];
    state.menuActions = normalizeMenuActions(menuActions);
  }
}

function cancelDeferredBatch() {
  state.deferredItems = [];
  state.deferredBatch = null;
  state.staffAuthorization = null;
  state.quickReplies = [];
  state.menuActions = [];
  closeOptionDialog();
  renderQuickReplies();
  saveState();
  announce(tr('batchCancelled'));
  $('#messageInput').focus();
}

function renderQuickReplies() {
  const wrap = $('#quickReplies'); wrap.replaceChildren();
  if (!state.history.length) renderLanguageChoices(wrap);

  if (state.deferredItems.length) {
    state.deferredBatch = normalizeDeferredBatch(state.deferredBatch);
    const current = Math.min(
      state.deferredBatch.total,
      state.deferredBatch.completed + 1,
    );
    const progress = document.createElement('div'); progress.className = 'deferred-progress'; progress.setAttribute('role', 'status');
    const title = document.createElement('strong'); title.textContent = tr('batchProgress', { current, total: state.deferredBatch.total });
    const detail = document.createElement('span'); detail.textContent = tr('batchPending');
    progress.append(title, detail); wrap.appendChild(progress);

    const proposal = state.deferredItems[0];
    const menu = state.menu.find((item) => item.id === proposal.menu_id);
    if (menu) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'option-action-chip proposal-chip current';
      button.textContent = `${current}/${state.deferredBatch.total} · ${tr('selectOptionsFor', { name: menuDisplayName(menu) })} ×${proposal.qty}`;
      button.disabled = state.staffVerificationRequired;
      button.onclick = () => openOptionDialog(menu.id, null, proposal); wrap.appendChild(button);
    }
    const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'batch-cancel-chip'; cancel.textContent = tr('cancelBatch');
    cancel.onclick = cancelDeferredBatch; wrap.appendChild(cancel);
    return;
  }

  state.quickReplies.forEach((reply) => {
    if (!reply || !reply.label) return;
    const button = document.createElement('button'); button.type = 'button'; button.textContent = reply.label;
    button.onclick = () => sendMessage(reply.value || reply.label); wrap.appendChild(button);
  });
  state.menuActions.forEach((menuId) => {
    const menu = state.menu.find((item) => item.id === menuId);
    if (!menu) return;
    const button = document.createElement('button'); button.type = 'button'; button.className = 'option-action-chip';
    button.textContent = tr('selectOptionsFor', { name: menuDisplayName(menu) });
    button.onclick = () => openOptionDialog(menuId); wrap.appendChild(button);
  });
}

function renderStaffRetryButton() {
  const wrap = $('#quickReplies'); wrap.replaceChildren();
  const button = document.createElement('button'); button.type = 'button'; button.textContent = tr('staffRetry');
  button.onclick = retryPendingStaffRequest; wrap.appendChild(button);
}

function cartForRequest() {
  return state.cart.map(({ menu_id, variant_id, qty, bean, extra_shots, milk, sweetness, ice, warming }) =>
    ({ menu_id, variant_id, qty, bean, extra_shots, milk, sweetness, ice, warming }));
}

function historyForRequest(history = state.history) {
  return (Array.isArray(history) ? history : [])
    .filter((message) => message && (message.role === 'user' || message.role === 'assistant'))
    .map((message) => ({ role: message.role, content: String(message.content || '').trim().slice(0, 4000) }))
    .filter((message) => message.content).slice(-8);
}

function chatHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (openAIAPIKey) headers['X-OpenAI-API-Key'] = openAIAPIKey;
  return headers;
}

function applyServerState(data) {
  if (data.cart) {
    state.cart = Array.isArray(data.cart.items) ? data.cart.items : [];
    const incomingOrderNo = data.cart.order_no || null;
    if (state.lastCheckout && state.lastCheckout.order_no !== incomingOrderNo) state.lastCheckout = null;
    state.orderNo = incomingOrderNo;
    state.cartStatus = data.cart.status || null;
    state.staffChecked = Boolean(data.cart.staff_checked);
  }
  if (Object.hasOwn(data, 'state_token')) state.stateToken = data.state_token || null;
  const tableId = Number(data.table_id || (data.cart && data.cart.table_id));
  if (Number.isInteger(tableId) && tableId >= 1 && tableId <= 12) {
    state.tableId = tableId;
    $('#tableSelect').value = String(tableId);
    $('#tableBadge').textContent = `TABLE ${String(tableId).padStart(2, '0')}`;
  }
  if (Array.isArray(data.sources)) state.sources = data.sources;
  if (Object.hasOwn(data, 'staff_challenge')) state.staffChallenge = data.staff_challenge || null;
}

function makeChoiceLabel(input, title, detail = '') {
  const label = document.createElement('label');
  const copy = document.createElement('span');
  const strong = document.createElement('b'); strong.textContent = title; copy.appendChild(strong);
  if (detail) { const small = document.createElement('small'); small.textContent = detail; copy.appendChild(small); }
  label.append(input, copy); return label;
}

function openOptionDialog(menuId, editIndex = null, preset = null, context = {}) {
  const item = state.menu.find((entry) => entry.id === menuId);
  if (!item) return;
  state.optionItem = item;
  state.optionEditIndex = Number.isInteger(editIndex) ? editIndex : null;
  state.optionPreset = state.optionEditIndex == null && preset ? { ...preset } : null;
  state.pairingChoice = null;
  state.pairingTrail = Array.isArray(context.pairingTrail) && context.pairingTrail.length
    ? [...new Set(context.pairingTrail.map((id) => String(id).toUpperCase()))]
    : [item.id];
  const current = state.optionEditIndex == null ? state.optionPreset : state.cart[state.optionEditIndex];
  state.optionBaseVariantId = (current && current.variant_id) || (item.variants[0] && item.variants[0].id);
  renderOptionDialog();
  openDialog($('#optionModal'));
  requestAnimationFrame(() => $('input', $('#variantChoices'))?.focus());
}

function renderOptionDialog() {
  const item = state.optionItem;
  if (!item) return;
  const current = state.optionEditIndex == null ? state.optionPreset : state.cart[state.optionEditIndex];
  const displayName = menuDisplayName(item);
  $('#optionTitle').textContent = tr('optionSelectTitle', { name: displayName });
  $('#optionMenuName').textContent = displayName;
  $('#optionMenuDescription').textContent = state.locale === 'ko' ? (item.description || item.ingredients || '') : '';
  $('#optionMenuDescription').hidden = state.locale !== 'ko';
  $('#optionMenuAllergens').textContent = `${tr('allergens')}: ${localizedAllergens(item.allergens)}`;
  $('#optionMenuImage').src = canonicalImage(item.id);
  $('#optionMenuImage').alt = tr('photoAlt', { name: displayName });
  $('#optionSubmit').textContent = state.optionEditIndex == null ? tr('addToCart') : tr('saveChanges');
  $('#optionError').textContent = '';

  const variants = $('#variantChoices'); variants.replaceChildren();
  (item.variants || []).forEach((variant, index) => {
    const input = document.createElement('input'); input.type = 'radio'; input.name = 'menuVariant'; input.value = variant.id;
    input.checked = current ? current.variant_id === variant.id : index === 0;
    input.addEventListener('change', updateOptionPrice);
    variants.appendChild(makeChoiceLabel(input, variantLabel(variant), variant.volume ? `${variant.volume}${variant.unit || ''}` : ''));
  });

  const optionWrap = $('#optionChoices'); optionWrap.replaceChildren();
  const options = item.options || {};
  Object.entries(options).forEach(([key, choices]) => {
    if (!Array.isArray(choices) || !choices.length) return;
    const fieldset = document.createElement('fieldset'); fieldset.dataset.optionKey = key;
    const legend = document.createElement('legend'); legend.textContent = optionFieldLabel(key);
    const select = document.createElement('select'); select.id = `option-${key}`; select.dataset.optionKey = key;
    choices.forEach((choice, index) => {
      const option = document.createElement('option'); option.value = String(choice.value); option.dataset.surcharge = Number(choice.surcharge || 0);
      option.textContent = `${localizedOptionValue(key, choice.value, choice.label)}${choice.surcharge ? ` (+${won(choice.surcharge)})` : ''}`;
      const selectedValue = current && current[key] != null ? String(current[key]) : String(choices[0].value);
      option.selected = String(choice.value) === selectedValue || (!choices.some((entry) => String(entry.value) === selectedValue) && index === 0);
      select.appendChild(option);
    });
    select.addEventListener('change', updateOptionPrice);
    fieldset.append(legend, select); optionWrap.appendChild(fieldset);
  });

  const quantity = $('#optionQuantity'); quantity.replaceChildren();
  for (let count = 1; count <= 10; count += 1) {
    const option = document.createElement('option'); option.value = count; option.textContent = String(count); option.selected = count === Number(current ? current.qty : 1); quantity.appendChild(option);
  }
  quantity.onchange = updateOptionPrice;
  updateOptionPrice();
}

function selectedVariant() {
  const id = $('input[name="menuVariant"]:checked', $('#optionForm'))?.value;
  return state.optionItem && (state.optionItem.variants || []).find((variant) => variant.id === id);
}

function addSuggestionRow(container, text, onAccept, onSkip, selected = false) {
  const row = document.createElement('div'); row.className = 'suggestion-row';
  const copy = document.createElement('span'); copy.textContent = text;
  const actions = document.createElement('div');
  const accept = document.createElement('button'); accept.type = 'button'; accept.textContent = tr('accept');
  const skip = document.createElement('button'); skip.type = 'button'; skip.className = 'quiet-button'; skip.textContent = tr('skip');
  const status = document.createElement('small'); status.setAttribute('aria-live', 'polite');
  accept.classList.toggle('selected', selected);
  if (selected) status.textContent = tr('suggestionAccepted');
  accept.onclick = () => { onAccept(); status.textContent = tr('suggestionAccepted'); accept.classList.add('selected'); };
  skip.onclick = () => { onSkip(); status.textContent = tr('suggestionSkipped'); accept.classList.remove('selected'); };
  actions.append(accept, skip); row.append(copy, actions, status); container.appendChild(row);
}

function renderSuggestions() {
  const previous = $('#optionSuggestions');
  if (previous) previous.remove();
  const item = state.optionItem;
  const variant = selectedVariant();
  if (!item || !variant || state.optionEditIndex != null) return;
  const box = document.createElement('section'); box.id = 'optionSuggestions'; box.className = 'option-suggestions';
  const heading = document.createElement('h3'); heading.textContent = tr('suggestions'); box.appendChild(heading);
  let count = 0;

  const larger = (item.variants || [])
    .filter((entry) => entry.temp === variant.temp && Number(entry.price) > Number(variant.price))
    .sort((a, b) => Number(a.price) - Number(b.price))[0];
  if (larger) {
    count += 1;
    addSuggestionRow(box, tr('sizeUp', { size: larger.size, price: won(Number(larger.price) - Number(variant.price)) }), () => {
      const radio = $(`input[name="menuVariant"][value="${larger.id}"]`, $('#optionForm'));
      if (radio) { radio.checked = true; updateOptionPrice(); }
    }, () => {
      const radio = $(`input[name="menuVariant"][value="${variant.id}"]`, $('#optionForm'));
      if (radio) { radio.checked = true; updateOptionPrice(); }
    });
  }

  const shots = $('#option-extra_shots');
  if (shots && [...shots.options].some((option) => option.value === '1')) {
    count += 1;
    const oneShot = [...shots.options].find((option) => option.value === '1');
    addSuggestionRow(box, tr('addShot', { price: won(Number(oneShot.dataset.surcharge || 0)) }), () => {
      shots.value = '1'; updateOptionPrice();
    }, () => { shots.value = '0'; updateOptionPrice(); });
  }

  const pairingExclusions = new Set([
    ...state.cart.map((entry) => entry.menu_id),
    ...state.deferredItems.map((entry) => entry.menu_id),
    ...(state.deferredBatch && Array.isArray(state.deferredBatch.menuIds) ? state.deferredBatch.menuIds : []),
    ...state.pairingTrail,
  ]);
  const pairingId = (item.pairing_ids || []).find((id) => (
    !pairingExclusions.has(id) && state.menu.some((entry) => entry.id === id)
  ));
  const pairing = state.menu.find((entry) => entry.id === pairingId);
  const hasMoreRequestedItems = Boolean(state.optionPreset && state.deferredItems.length > 1);
  if (pairing && !hasMoreRequestedItems) {
    count += 1;
    const price = Math.min(...(pairing.variants || []).map((entry) => Number(entry.price)).filter(Number.isFinite));
    addSuggestionRow(box, tr('pairing', { name: menuDisplayName(pairing), price: won(price) }), () => {
      state.pairingChoice = pairing.id;
    }, () => { state.pairingChoice = null; }, state.pairingChoice === pairing.id);
  }
  if (count) $('#optionGuidance').before(box);
}

function updateOptionPrice() {
  const variant = selectedVariant();
  if (!variant) return;
  const iceField = $('[data-option-key="ice"]', $('#optionChoices'));
  if (iceField) iceField.hidden = variant.temp !== 'ICED';
  let unit = Number(variant.price || 0);
  $$('select[data-option-key]', $('#optionChoices')).forEach((select) => {
    if (select.closest('fieldset').hidden) return;
    unit += Number(select.selectedOptions[0]?.dataset.surcharge || 0);
  });
  $('#optionPrice').textContent = won(unit * Number($('#optionQuantity').value || 1));
  renderSuggestions();
}

function optionItemPayload() {
  const variant = selectedVariant();
  if (!variant) return null;
  const item = {
    menu_id: state.optionItem.id, variant_id: variant.id,
    qty: Number($('#optionQuantity').value || 1), extra_shots: 0,
    bean: null, milk: null, sweetness: null, ice: null, warming: null,
  };
  $$('select[data-option-key]', $('#optionChoices')).forEach((select) => {
    if (select.closest('fieldset').hidden) return;
    const key = select.dataset.optionKey;
    item[key] = key === 'extra_shots' ? Number(select.value) : select.value;
  });
  return item;
}

async function cartAction(action, fields = {}, { silent = false } = {}) {
  if (state.busy) return false;
  // A staff authorization is scoped to the approved purchase and must survive
  // the option modal. It is consumed only by the first matching alcohol change.
  const staffAuthorization = cartActionNeedsAlcoholApproval(action, fields)
    ? state.staffAuthorization : null;
  const rollback = {
    cart: state.cart.map((item) => ({ ...item })), stateToken: state.stateToken, cartStatus: state.cartStatus,
    staffChecked: state.staffChecked, orderNo: state.orderNo,
  };
  state.busy = true;
  $('#sendButton').disabled = true;
  try {
    const response = await fetch('/api/cart/action', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action, table_id: state.tableId, cart: cartForRequest(), state_token: state.stateToken,
        staff_authorization: staffAuthorization, language: state.locale, ...fields,
      }),
    });
    const data = await responsePayload(response);
    if (!response.ok) throw new Error(errorMessage(data.detail, tr('cartActionFailed')));
    applyServerState(data);
    state.staffVerificationRequired = Boolean(data.requires_staff_verification);
    state.staffVerificationReason = data.staff_verification_reason || null;
    if (staffAuthorization || state.staffVerificationRequired) state.staffAuthorization = null;
    if (state.staffVerificationRequired) {
      state.pendingStaffRequest = null;
      state.pendingCartRollback = rollback;
      if (!silent) appendMessage('assistant', `${tr('staffNeeded')}\n${tr('staffCodeChatPrompt')}`, false);
    } else if (!cartHasAlcohol()) {
      state.staffChallenge = null;
      state.staffChecked = false;
      state.pendingCartRollback = null;
    } else {
      state.pendingCartRollback = null;
    }
    renderCart();
    if (state.staffVerificationRequired) revealStaffVerification();
    else renderStaffStatus();
    saveState();
    $('#cartError').textContent = '';
    if (!silent) announce(tr('cartUpdated'));
    return true;
  } catch (error) {
    const target = $('#optionModal').open
      ? $('#optionError')
      : $('#checkoutModal').open ? $('#checkoutError') : $('#cartError');
    if (target) target.textContent = error.message;
    announce(`${tr('cartActionFailed')} ${error.message}`);
    return false;
  } finally {
    state.busy = false; $('#sendButton').disabled = false;
  }
}

async function submitOption(event) {
  event.preventDefault();
  const payload = optionItemPayload();
  if (!payload) return;
  $('#optionError').textContent = '';
  const submit = $('#optionSubmit'); submit.disabled = true;
  const action = state.optionEditIndex == null ? 'add' : 'replace';
  const menuName = menuDisplayName(state.optionItem);
  const pairingId = action === 'add' ? state.pairingChoice : null;
  const pairingTrail = [...state.pairingTrail];
  const completedPreset = state.optionPreset;
  const fields = action === 'add' ? { item: payload } : { item: payload, index: state.optionEditIndex };
  const success = await cartAction(action, fields);
  submit.disabled = false;
  if (!success) return;
  if (completedPreset) {
    const completedIndex = state.deferredItems.findIndex((proposal) => proposalKey(proposal) === proposalKey(completedPreset));
    if (completedIndex >= 0) {
      state.deferredItems.splice(completedIndex, 1);
      if (state.deferredBatch) state.deferredBatch.completed += 1;
    }
  }
  if (!state.deferredItems.length) {
    state.deferredBatch = null;
    state.staffAuthorization = null;
  }
  renderQuickReplies();
  closeOptionDialog();
  saveState();
  announce(tr('addedToCart', { name: menuName }));
  if (pairingId && !state.staffVerificationRequired) {
    announce(tr('pairingNext'));
    openOptionDialog(pairingId, null, null, { pairingTrail: [...pairingTrail, pairingId] });
  } else if (state.deferredItems.length && !state.staffVerificationRequired) {
    const next = state.deferredItems[0];
    openOptionDialog(next.menu_id, null, next);
  }
}

async function sendMessage(rawMessage, options = {}) {
  const message = String(rawMessage || '').trim();
  if (!message || state.busy) return;
  if (state.staffVerificationRequired) { revealStaffVerification(); return; }
  if (state.deferredItems.length) {
    renderQuickReplies();
    announce(tr('batchPending'));
    if (!$('#optionModal').open && !$$('dialog[open]').length) {
      const next = state.deferredItems[0];
      openOptionDialog(next.menu_id, null, next);
    }
    return;
  }
  applyDetectedLocale(message);
  if (state.orderNo && isAdditionalOrderRequest(message)) startAdditionalOrder();
  if (!openAIAPIKey && !state.serverAIReady && !state.mockMode) { openAPIKeyModal(); return; }
  state.busy = true; $('#sendButton').disabled = true;
  state.quickReplies = []; state.menuActions = []; renderQuickReplies();
  const previousHistory = historyForRequest(Array.isArray(options.historyOverride) ? options.historyOverride : state.history);
  if (options.appendUser !== false) {
    appendMessage('user', message); $('#messageInput').value = ''; saveState();
  }
  const thinking = document.createElement('div'); thinking.className = 'message assistant thinking';
  const body = document.createElement('div'); body.className = 'message-body';
  const speaker = document.createElement('div'); speaker.className = 'speaker'; speaker.textContent = 'Moki';
  const bubble = document.createElement('div'); bubble.className = 'bubble'; bubble.textContent = tr('thinking');
  body.append(speaker, bubble); thinking.append(createAvatar(), body); $('#messages').appendChild(thinking);
  $('#messages').scrollTop = $('#messages').scrollHeight;
  try {
    const response = await fetch('/api/chat', {
      method: 'POST', headers: chatHeaders(),
      body: JSON.stringify({
        message, history: previousHistory, cart: cartForRequest(), state_token: state.stateToken,
        staff_authorization: options.staffAuthorization || null, table_id: state.tableId, language: state.locale,
        defer_cart_add: true,
      }),
    });
    const data = await responsePayload(response);
    if (data.requires_staff_verification) {
      thinking.remove();
      applyServerState(data);
      appendMessage('assistant', `${tr('staffNeeded')}\n${tr('staffCodeChatPrompt')}`, false);
      state.staffVerificationRequired = true;
      state.staffVerificationReason = data.staff_verification_reason || 'alcohol_purchase';
      state.staffAuthorization = null;
      state.pendingStaffRequest = { message, history: previousHistory };
      renderCart(); renderSources(); renderQuickReplies(); revealStaffVerification(); saveState();
      return;
    }
    if (!response.ok) throw new Error(errorMessage(data.detail, tr('answerFailed')));
    thinking.remove();
    appendMessage('assistant', data.reply || tr('answerFailed'), true, data.menu_images);
    applyServerState(data);
    setResponseChoices(data.quick_replies, data.menu_actions, data.deferred_cart_items);
    state.staffVerificationRequired = false; state.staffVerificationReason = null;
    state.staffChallenge = null;
    const returnedStaffAuthorization = data.staff_authorization || options.staffAuthorization || null;
    const hasAuthorizedMenuSelection = Boolean(data.staff_authorization) || state.deferredItems.length
      || data.open_option_menu_id || state.menuActions.length;
    state.staffAuthorization = hasAuthorizedMenuSelection ? returnedStaffAuthorization : null;
    state.pendingStaffRequest = null;
    renderCart(); renderStaffStatus(); renderSources(); renderQuickReplies(); saveState();
    if (state.deferredItems.length) openOptionDialog(state.deferredItems[0].menu_id, null, state.deferredItems[0]);
    else if (data.open_order_form) openCheckout();
    else if (data.open_option_menu_id) openOptionDialog(String(data.open_option_menu_id).toUpperCase());
  } catch (error) {
    if (thinking.isConnected) thinking.remove();
    appendMessage('assistant', `${tr('checkConnection')} ${error.message}`, false);
    if (/API|key|키/i.test(String(error.message))) openAPIKeyModal();
    if (options.staffAuthorization && state.pendingStaffRequest) renderStaffRetryButton();
  } finally {
    state.busy = false; $('#sendButton').disabled = false;
    if (!$$('dialog[open]').length && !state.staffVerificationRequired) $('#messageInput').focus();
  }
}

async function retryPendingStaffRequest() {
  const pending = state.pendingStaffRequest;
  const authorization = state.staffAuthorization;
  if (!pending || !authorization || state.busy) return;
  await sendMessage(pending.message, { appendUser: false, historyOverride: pending.history, staffAuthorization: authorization });
}

async function cancelStaffVerification() {
  if (state.busy) return;
  if (!state.pendingStaffRequest && state.pendingCartRollback) {
    const rollback = state.pendingCartRollback;
    state.cart = Array.isArray(rollback.cart) ? rollback.cart : [];
    state.stateToken = rollback.stateToken || null;
    state.cartStatus = rollback.cartStatus || null;
    state.staffChecked = Boolean(rollback.staffChecked);
    state.orderNo = rollback.orderNo || null;
  }
  state.staffVerificationRequired = false; state.staffVerificationReason = null;
  state.staffChallenge = null; state.staffAuthorization = null; state.pendingStaffRequest = null; state.pendingCartRollback = null;
  $('#staffCodeInput').value = '';
  appendMessage('assistant', tr('alcoholCancelled'));
  closeDialog($('#staffCodeModal'));
  renderStaffStatus(); renderQuickReplies(); renderCart(); saveState(); $('#messageInput').focus();
}

async function verifyStaff() {
  if (state.busy) return;
  const button = $('#staffVerifyButton'); const status = $('#staffStatus');
  const staffCode = $('#staffCodeInput').value.trim();
  if (!/^\d{4}$/.test(staffCode)) {
    status.className = 'setting-note error'; status.textContent = tr('codeFourDigits'); $('#staffCodeInput').focus(); return;
  }
  let retryRequest = null; let refreshRequest = null;
  state.busy = true; button.disabled = true; status.className = 'setting-note'; status.textContent = tr('staffProcessing');
  try {
    const response = await fetch('/api/staff/verify', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Moki-Staff-Code': staffCode },
      body: JSON.stringify({ table_id: state.tableId, cart: cartForRequest(), state_token: state.stateToken, staff_challenge: state.staffChallenge, language: state.locale }),
    });
    const data = await responsePayload(response);
    if (!response.ok && response.status === 410 && state.pendingStaffRequest) {
      refreshRequest = state.pendingStaffRequest;
      state.staffVerificationRequired = false; state.staffVerificationReason = null;
      state.staffChallenge = null; state.staffAuthorization = null; state.pendingStaffRequest = null;
      status.textContent = tr('staffProcessing'); saveState();
    } else {
      if (!response.ok) throw new Error(errorMessage(data.detail, tr('staffNeeded')));
      applyServerState(data);
      state.staffVerificationRequired = false; state.staffVerificationReason = null; state.staffChallenge = null;
      retryRequest = state.pendingStaffRequest;
      // A chat preflight still has to pass through the deferred option modal;
      // an already-mutated cart is complete as soon as staff verifies it.
      state.staffAuthorization = retryRequest ? (data.staff_authorization || null) : null;
      state.pendingCartRollback = null;
      renderCart(); renderStaffStatus(tr('staffDone')); saveState();
    }
  } catch (error) {
    status.className = 'setting-note error'; status.textContent = error.message; $('#staffCodeInput').focus();
  } finally {
    $('#staffCodeInput').value = ''; state.busy = false; button.disabled = false;
  }
  if (!state.staffVerificationRequired && !refreshRequest) closeDialog($('#staffCodeModal'));
  if (refreshRequest) await sendMessage(refreshRequest.message, { appendUser: false, historyOverride: refreshRequest.history });
  else if (retryRequest) await retryPendingStaffRequest();
  else if (!state.staffVerificationRequired && state.deferredItems.length) {
    renderQuickReplies(); saveState();
    if (!$$('dialog[open]').length) {
      const next = state.deferredItems[0];
      openOptionDialog(next.menu_id, null, next);
    }
  }
}

function localizedTableChangeMessage(table) {
  return {
    ko: `좌석을 ${table}번으로 변경해줘`, en: `Change table to ${table}`,
    zh: `更改座位为 ${table} 号`, ja: `席を ${table} 番に変更`,
  }[state.locale];
}

async function changeTable(nextTable) {
  const table = Number(nextTable);
  const oldTable = state.tableId;
  if (!Number.isInteger(table) || table === oldTable || state.busy) return;
  if (state.staffVerificationRequired) {
    $('#tableSelect').value = String(oldTable); revealStaffVerification(); announce(tr('staffNeeded')); return;
  }
  state.busy = true; $('#tableSelect').disabled = true; announce(tr('tableChanging'));
  try {
    const response = await fetch('/api/chat', {
      method: 'POST', headers: chatHeaders(),
      body: JSON.stringify({
        message: localizedTableChangeMessage(table), history: historyForRequest(), cart: cartForRequest(),
        state_token: state.stateToken, staff_authorization: null, table_id: oldTable, language: state.locale,
      }),
    });
    const data = await responsePayload(response);
    if (!response.ok) throw new Error(errorMessage(data.detail, tr('tableChangeFailed')));
    applyServerState(data);
    appendMessage('assistant', data.reply, true);
    renderCart(); renderStaffStatus(); saveState(); announce(data.reply);
  } catch (error) {
    state.tableId = oldTable; $('#tableSelect').value = String(oldTable);
    announce(`${tr('tableChangeFailed')} ${error.message}`);
  } finally { state.busy = false; $('#tableSelect').disabled = false; }
}

function renderCheckoutReview() {
  const wrap = $('#checkoutReview'); wrap.replaceChildren();
  state.cart.forEach((item) => {
    const menu = state.menu.find((entry) => entry.id === item.menu_id);
    const row = document.createElement('div'); row.className = 'checkout-review-line';
    const image = document.createElement('img'); image.src = canonicalImage(item.menu_id); image.alt = tr('photoAlt', { name: menu ? menuDisplayName(menu) : item.name });
    const copy = document.createElement('div');
    const name = document.createElement('b'); name.textContent = `${menu ? menuDisplayName(menu) : item.name} ×${item.qty}`;
    const details = document.createElement('small'); details.textContent = cartOptionText(item);
    copy.append(name, details); const price = document.createElement('strong'); price.textContent = won(item.subtotal);
    row.append(image, copy, price); wrap.appendChild(row);
  });
  const subtotal = state.cart.reduce((sum, item) => sum + Number(item.subtotal || 0), 0);
  $('#benefitBeforeAmount').textContent = won(subtotal);
  $('#benefitDiscountAmount').textContent = won(0);
  $('#benefitAfterAmount').textContent = won(subtotal);
  $('#checkoutTotal').textContent = won(subtotal);
}

function normalizeCheckoutReceipt(raw) {
  if (!raw || typeof raw !== 'object' || raw.simulated !== true) return null;
  const orderNo = String(raw.order_no || '').trim().slice(0, 120);
  if (!orderNo) return null;
  const tableId = Number(raw.table_id);
  const items = (Array.isArray(raw.items) ? raw.items : []).slice(0, 30).map((item) => ({
    menu_id: String(item && item.menu_id || '').toUpperCase().slice(0, 20),
    variant_id: String(item && item.variant_id || '').slice(0, 80),
    name: String(item && item.name || '').slice(0, 160),
    qty: Math.max(1, Math.min(10, Number(item && item.qty || 1))),
    subtotal: Math.max(0, Number(item && item.subtotal || 0)),
    temp: item && item.temp, size: item && item.size,
    bean: item && item.bean, extra_shots: Number(item && item.extra_shots || 0),
    milk: item && item.milk, sweetness: item && item.sweetness,
    ice: item && item.ice, warming: item && item.warming,
  })).filter((item) => item.menu_id);
  const totalBefore = Math.max(0, Number(raw.total_before_discount || 0));
  const discount = Math.max(0, Number(raw.discount || 0));
  const totalDue = Math.max(0, Number(raw.total_due ?? (totalBefore - discount)));
  return {
    simulated: true,
    order_no: orderNo,
    table_id: Number.isInteger(tableId) && tableId >= 1 && tableId <= 12 ? tableId : state.tableId,
    items,
    total_before_discount: totalBefore,
    discount,
    total_due: totalDue,
    payment_method: ['card', 'mobile', 'gifticon'].includes(raw.payment_method) ? raw.payment_method : 'card',
    receipt: ['paper', 'digital', 'none'].includes(raw.receipt) ? raw.receipt : 'none',
  };
}

function paymentMethodLabel(value) {
  return tr({ card: 'card', mobile: 'mobilePay', gifticon: 'gifticon' }[value] || 'card');
}

function receiptChoiceLabel(value) {
  return tr({ paper: 'paperReceipt', digital: 'digitalReceipt', none: 'noReceipt' }[value] || 'noReceipt');
}

function renderCheckoutReceipt(raw = state.lastCheckout) {
  const checkout = normalizeCheckoutReceipt(raw);
  if (!checkout) return;
  const items = $('#receiptItems'); items.replaceChildren();
  checkout.items.forEach((item) => {
    const menu = state.menu.find((entry) => entry.id === item.menu_id);
    const line = document.createElement('article'); line.className = 'receipt-item-line';
    const copy = document.createElement('div');
    const name = document.createElement('b');
    name.textContent = `${menu ? menuDisplayName(menu) : (item.name || item.menu_id)} ×${item.qty}`;
    const options = document.createElement('small'); options.textContent = cartOptionText(item);
    const subtotal = document.createElement('strong'); subtotal.textContent = won(item.subtotal);
    subtotal.setAttribute('aria-label', `${tr('subtotal')} ${won(item.subtotal)}`);
    copy.append(name, options); line.append(copy, subtotal); items.appendChild(line);
  });
  $('#receiptCallout').textContent = tr('receiptCallout', { number: checkout.order_no });
  $('#receiptTable').textContent = tr('tableOption', { n: checkout.table_id });
  $('#receiptBeforeDiscount').textContent = won(checkout.total_before_discount);
  $('#receiptDiscount').textContent = won(checkout.discount);
  $('#receiptPaidAmount').textContent = won(checkout.total_due);
  $('#receiptPaymentMethod').textContent = paymentMethodLabel(checkout.payment_method);
  $('#receiptChoice').textContent = receiptChoiceLabel(checkout.receipt);
  $('#receiptBenefitApplied').textContent = tr('benefitNotApplied');
  $('#orderNumber').textContent = checkout.order_no;
}

function renderCupChoices() {
  const takeoutInput = $('input[name="serviceMode"][value="takeout"]', $('#checkoutForm'));
  const dineInInput = $('input[name="serviceMode"][value="dine_in"]', $('#checkoutForm'));
  const hasAlcohol = cartHasAlcohol();
  takeoutInput.disabled = hasAlcohol;
  takeoutInput.closest('label').classList.toggle('disabled', hasAlcohol);
  if (hasAlcohol && takeoutInput.checked) dineInInput.checked = true;
  const mode = $('input[name="serviceMode"]:checked', $('#checkoutForm'))?.value || 'dine_in';
  const previous = $('input[name="cup"]:checked', $('#checkoutForm'))?.value;
  const choices = mode === 'dine_in'
    ? [['store', tr('storeCup')], ['personal', tr('personalCup')]]
    : [['personal', tr('personalCup')], ['disposable', tr('disposableCup')]];
  const wrap = $('#cupChoices'); wrap.replaceChildren();
  choices.forEach(([value, label], index) => {
    const input = document.createElement('input'); input.type = 'radio'; input.name = 'cup'; input.value = value;
    input.checked = choices.some(([candidate]) => candidate === previous) ? value === previous : index === 0;
    wrap.appendChild(makeChoiceLabel(input, label));
  });
  const carrier = $('input[name="supplies"][value="carrier"]', $('#checkoutForm'));
  carrier.disabled = mode !== 'takeout';
  carrier.closest('label').classList.toggle('disabled', carrier.disabled);
  if (carrier.disabled) carrier.checked = false;
}

function openCheckout() {
  if (!state.cart.length) { announce(tr('cartEmptyCheckout')); $('#confirmButton').focus(); return; }
  if (cartHasAlcohol() && !state.staffChecked) {
    state.staffVerificationRequired = true;
    appendMessage('assistant', `${tr('staffNeeded')}\n${tr('staffCodeChatPrompt')}`, false);
    revealStaffVerification();
    announce(`${tr('staffNeeded')} ${tr('staffCodeChatPrompt')}`); saveState(); return;
  }
  const completed = normalizeCheckoutReceipt(state.lastCheckout);
  if (completed && completed.order_no === state.orderNo) {
    state.lastCheckout = completed;
    $('#checkoutFormBody').hidden = true; $('#orderSuccess').hidden = false;
    $('#checkoutError').textContent = '';
    renderCheckoutReceipt(completed);
    openDialog($('#checkoutModal'));
    return;
  }
  $('#checkoutFormBody').hidden = false; $('#orderSuccess').hidden = true; $('#checkoutError').textContent = '';
  renderCheckoutReview(); renderCupChoices();
  $('#splitCountWrap').hidden = $('input[name="splitMode"]:checked', $('#checkoutForm'))?.value !== 'equal';
  openDialog($('#checkoutModal'));
}

function startAdditionalOrder() {
  if (!state.orderNo || state.busy) return;
  state.cart = []; state.orderNo = null; state.stateToken = null; state.cartStatus = null;
  state.staffChecked = false; state.staffVerificationRequired = false;
  state.staffVerificationReason = null; state.staffChallenge = null; state.staffAuthorization = null;
  state.pendingStaffRequest = null; state.pendingCartRollback = null;
  state.quickReplies = []; state.menuActions = [];
  state.deferredItems = []; state.deferredBatch = null;
  state.optionItem = null; state.optionEditIndex = null; state.optionPreset = null;
  state.pairingChoice = null; state.pairingTrail = []; state.lastCheckout = null;
  $('#checkoutForm').reset();
  $('#cartError').textContent = ''; $('#optionError').textContent = ''; $('#checkoutError').textContent = '';
  closeDialog($('#checkoutModal'));
  renderCart(); renderStaffStatus(); renderQuickReplies();
  appendMessage('assistant', tr('additionalOrderStarted'));
  saveState(); announce(tr('additionalOrderStarted'));
  $('#messageInput').focus();
}

async function submitCheckout(event) {
  event.preventDefault();
  if (state.busy) return;
  const form = $('#checkoutForm');
  const serviceMode = $('input[name="serviceMode"]:checked', form)?.value;
  const cup = $('input[name="cup"]:checked', form)?.value;
  const paymentMethod = $('input[name="paymentMethod"]:checked', form)?.value;
  const splitMode = $('input[name="splitMode"]:checked', form)?.value;
  const receipt = $('input[name="receipt"]:checked', form)?.value;
  const supplies = $$('input[name="supplies"]:checked', form).map((input) => input.value);
  const splitCount = splitMode === 'equal' ? Number($('#splitCount').value || 2) : 1;
  const button = $('#checkoutSubmit');
  state.busy = true; button.disabled = true; button.textContent = tr('confirming'); $('#checkoutError').textContent = '';
  try {
    const response = await fetch('/api/order/confirm', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        table_id: state.tableId, cart: cartForRequest(), state_token: state.stateToken,
        service_mode: serviceMode, cup, supplies, payment_method: paymentMethod,
        split_mode: splitMode, split_count: splitCount, receipt, language: state.locale,
      }),
    });
    const data = await responsePayload(response);
    if (!response.ok) throw new Error(errorMessage(data.detail, tr('retryCheckout')));
    if (!data.checkout || data.checkout.simulated !== true) throw new Error(tr('retryCheckout'));
    applyServerState(data);
    state.lastCheckout = normalizeCheckoutReceipt({
      ...data.checkout,
      order_no: data.order_no || state.orderNo,
      table_id: data.table_id || state.tableId,
      items: state.cart.map((item) => ({ ...item })),
    });
    if (!state.lastCheckout) throw new Error(tr('retryCheckout'));
    renderCart(); saveState();
    $('#checkoutFormBody').hidden = true; $('#orderSuccess').hidden = false;
    renderCheckoutReceipt(state.lastCheckout);
    announce(`${tr('orderComplete')}. ${tr('orderNotSubmitted')}`);
  } catch (error) {
    $('#checkoutError').textContent = `${error.message} ${tr('retryCheckout')}`;
    announce($('#checkoutError').textContent);
  } finally {
    state.busy = false; button.disabled = false; button.textContent = tr('confirmDemoOrder');
  }
}

function saveState() {
  sessionStorage.setItem(STATE_KEY, JSON.stringify({
    version: STORAGE_VERSION, history: state.history.slice(-20), cart: state.cart,
    orderNo: state.orderNo, stateToken: state.stateToken, cartStatus: state.cartStatus,
    staffChecked: state.staffChecked, staffCallRequested: state.staffCallRequested, tableId: state.tableId,
    staffVerificationRequired: state.staffVerificationRequired,
    staffChallenge: state.staffChallenge,
    pendingStaffRequest: state.staffVerificationRequired ? state.pendingStaffRequest : null,
    pendingCartRollback: state.staffVerificationRequired ? state.pendingCartRollback : null,
    deferredItems: state.deferredItems,
    deferredBatch: state.deferredBatch,
    lastCheckout: state.lastCheckout,
  }));
}

function restoreState() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STATE_KEY) || '{}');
    const current = saved.version === STORAGE_VERSION;
    state.history = (Array.isArray(saved.history) ? saved.history : [])
      .filter((message) => message && (message.role === 'user' || message.role === 'assistant'))
      .map((message) => ({
        role: message.role, content: String(message.content || '').slice(0, 4000),
        menu_images: message.role === 'assistant' ? normalizeMenuImages(message.menu_images) : [],
      })).filter((message) => message.content.trim()).slice(-20);
    state.cart = Array.isArray(saved.cart) ? saved.cart : [];
    state.orderNo = saved.orderNo || null; state.stateToken = saved.stateToken || null;
    state.cartStatus = typeof saved.cartStatus === 'string' ? saved.cartStatus : null;
    state.staffChecked = Boolean(saved.staffChecked && saved.stateToken);
    state.staffCallRequested = Boolean(current && saved.staffCallRequested);
    state.staffVerificationRequired = Boolean(current && saved.staffVerificationRequired && saved.staffChallenge);
    state.staffChallenge = current && typeof saved.staffChallenge === 'string' ? saved.staffChallenge : null;
    state.pendingStaffRequest = current && saved.pendingStaffRequest && typeof saved.pendingStaffRequest.message === 'string'
      ? { message: saved.pendingStaffRequest.message.slice(0, 2000), history: historyForRequest(saved.pendingStaffRequest.history) } : null;
    state.pendingCartRollback = current && saved.pendingCartRollback && Array.isArray(saved.pendingCartRollback.cart)
      ? saved.pendingCartRollback : null;
    state.deferredItems = current ? normalizeDeferredItems(saved.deferredItems) : [];
    state.deferredBatch = current ? normalizeDeferredBatch(saved.deferredBatch, state.deferredItems) : null;
    state.tableId = Number.isInteger(saved.tableId) && saved.tableId >= 1 && saved.tableId <= 12 ? saved.tableId : 5;
    state.lastCheckout = current ? normalizeCheckoutReceipt(saved.lastCheckout) : null;
    if (state.lastCheckout && state.lastCheckout.order_no !== state.orderNo) state.lastCheckout = null;
  } catch (_) { sessionStorage.removeItem(STATE_KEY); }
}

function prepareVisitState() {
  // Older releases persisted order history across visits.  Remove that legacy
  // record on every load.  A deliberate fresh navigation starts a clean kiosk,
  // while an accidental reload in the same tab may recover the active order.
  localStorage.removeItem(STATE_KEY);
  const navigation = performance.getEntriesByType?.('navigation')?.[0];
  if (!navigation || navigation.type !== 'reload') {
    sessionStorage.removeItem(STATE_KEY);
  }
}

function resetSession() {
  state.history = []; state.cart = []; state.orderNo = null; state.stateToken = null;
  state.cartStatus = null; state.staffChecked = false; state.staffCallRequested = false; state.staffVerificationRequired = false;
  state.staffVerificationReason = null; state.staffChallenge = null; state.staffAuthorization = null;
  state.pendingStaffRequest = null; state.pendingCartRollback = null;
  state.sources = []; state.quickReplies = []; state.menuActions = [];
  state.optionItem = null; state.optionEditIndex = null; state.optionPreset = null;
  state.deferredItems = []; state.deferredBatch = null; state.pairingChoice = null; state.pairingTrail = [];
  state.lastCheckout = null;
  localStorage.removeItem(STATE_KEY);
  sessionStorage.removeItem(STATE_KEY);
  $('#cartError').textContent = ''; $('#optionError').textContent = ''; $('#checkoutError').textContent = '';
  renderHistory(); renderCart(); renderStaffStatus(); renderStaffCallState(); renderSources(); renderQuickReplies(); announce(tr('resetDone'));
}

async function boot() {
  prepareVisitState(); loadPreferences(); restoreState(); applyAccessibility(); translateStaticPage();
  renderTableOptions(); renderHistory(); renderCart(); renderStaffStatus(); renderStaffCallState(); renderSources(); renderQuickReplies();
  for (let count = 2; count <= 10; count += 1) {
    const option = document.createElement('option'); option.value = count; option.textContent = String(count); $('#splitCount').appendChild(option);
  }
  if (!state.localeChosen) openDialog($('#languageModal'));
  try {
    const [healthResponse, menuResponse] = await Promise.all([fetch('/api/health'), fetch('/api/menu')]);
    const health = await responsePayload(healthResponse); const menu = await responsePayload(menuResponse);
    if (!healthResponse.ok || !health.ok || !menuResponse.ok) throw new Error(tr('connectionError'));
    state.contentReady = true; state.serverAIReady = Boolean(health.ai_ready); state.mockMode = Boolean(health.mock_mode);
    state.menu = Array.isArray(menu.items) ? menu.items : [];
    state.deferredItems = normalizeDeferredItems(state.deferredItems);
    state.deferredBatch = normalizeDeferredBatch(state.deferredBatch, state.deferredItems);
    state.categories = Array.isArray(menu.categories) ? menu.categories : [];
    if (!state.categories.includes(state.category)) state.category = state.categories[0] || '커피';
    refreshConnectionStatus(); renderCategories(); renderMenu(); renderCart(); renderStaffStatus();
    renderHistory(); renderQuickReplies(); saveState();
    scheduleAPIKeyModal();
  } catch (error) {
    setConnection('error', tr('connectionError'));
    const notice = document.createElement('div'); notice.className = 'loading-card'; notice.textContent = error.message;
    $('#menuGrid').replaceChildren(notice); scheduleAPIKeyModal();
  }
}

$('#chatForm').addEventListener('submit', (event) => { event.preventDefault(); sendMessage($('#messageInput').value); });
$('#optionForm').addEventListener('submit', submitOption);
$('#checkoutForm').addEventListener('submit', submitCheckout);
$('#confirmButton').addEventListener('click', openCheckout);
$('#additionalOrderCartButton').addEventListener('click', startAdditionalOrder);
$('#additionalOrderReceiptButton').addEventListener('click', startAdditionalOrder);
$('#tableSelect').addEventListener('change', (event) => changeTable(event.target.value));
$('#staffVerifyButton').addEventListener('click', verifyStaff);
$('#staffCancelButton').addEventListener('click', cancelStaffVerification);
$('#staffCallButton').addEventListener('click', openStaffCallDialog);
$('#staffCallConfirmButton').addEventListener('click', requestStaffCall);
$('#staffCallCancelButton').addEventListener('click', cancelStaffCall);
$('#staffCodeInput').addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); verifyStaff(); } });
$('#staffCodeModal').addEventListener('cancel', (event) => {
  event.preventDefault();
  revealStaffVerification();
});

$('#apiKeyButton').addEventListener('click', openAPIKeyModal);
$('#apiKeyForm').addEventListener('submit', submitAPIKey);
$('#apiKeyCancel').addEventListener('click', closeAPIKeyModal);
$('#apiKeyModal').addEventListener('cancel', (event) => {
  if (!(openAIAPIKey || state.serverAIReady || state.mockMode)) event.preventDefault();
  else closeAPIKeyModal();
});

$('#languageButton').addEventListener('click', () => { $('#languageClose').hidden = false; openDialog($('#languageModal')); });
$('#languageClose').addEventListener('click', () => closeDialog($('#languageModal')));
$$('[data-locale]').forEach((button) => button.addEventListener('click', () => setLocale(button.dataset.locale)));
$('#languageModal').addEventListener('cancel', (event) => {
  if (!state.localeChosen) event.preventDefault();
  else closeDialog($('#languageModal'));
});

$('#easyViewButton').addEventListener('click', () => openDialog($('#accessibilityModal')));
$('#largeTextToggle').addEventListener('change', (event) => setAccessibility('largeText', event.target.checked));
$('#highContrastToggle').addEventListener('change', (event) => setAccessibility('highContrast', event.target.checked));
$('#largeTargetsToggle').addEventListener('change', (event) => setAccessibility('largeTargets', event.target.checked));
$('#easyViewAll').addEventListener('click', () => {
  state.largeText = true; state.highContrast = true; state.largeTargets = true; applyAccessibility(); savePreferences();
});
$('#easyViewReset').addEventListener('click', () => {
  state.largeText = false; state.highContrast = false; state.largeTargets = false; applyAccessibility(); savePreferences();
});

$$('[data-close-dialog]').forEach((button) => button.addEventListener('click', () => {
  if (button.dataset.closeDialog === 'optionModal') closeOptionDialog();
  else closeDialog($(`#${button.dataset.closeDialog}`));
}));
$$('dialog').forEach((dialog) => dialog.addEventListener('close', syncModalState));
$('#optionModal').addEventListener('cancel', resetOptionDialogState);
$('#optionModal').addEventListener('close', () => {
  if (!$('#optionModal').open) resetOptionDialogState();
});

$$('input[name="serviceMode"]').forEach((input) => input.addEventListener('change', renderCupChoices));
$$('input[name="splitMode"]').forEach((input) => input.addEventListener('change', () => {
  const equal = $('input[name="splitMode"]:checked').value === 'equal';
  $('#splitCountWrap').hidden = !equal;
}));

$('#resetButton').addEventListener('click', resetSession);
$('#speakButton').addEventListener('click', () => {
  const last = [...state.history].reverse().find((message) => message.role === 'assistant');
  if (!last || !('speechSynthesis' in window)) return;
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(last.content); utterance.lang = SPEECH_LOCALES[state.locale]; speechSynthesis.speak(utterance);
});

window.addEventListener('pagehide', () => {
  openAIAPIKey = ''; state.staffAuthorization = null; $('#apiKeyInput').value = ''; $('#staffCodeInput').value = '';
});
window.addEventListener('pageshow', () => {
  refreshConnectionStatus();
  if (state.contentReady && state.localeChosen && !openAIAPIKey && !state.serverAIReady && !state.mockMode) scheduleAPIKeyModal();
});

boot();
