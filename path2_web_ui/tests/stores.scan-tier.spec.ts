// 顶栏 scan 档(view store):进出 scan 档时股票怎么带(spec 5.2「切档时股票怎么带」)、没加载扫描时的 no_scan、
// 从扫描列表选股清掉打开时给定的图窗。图表状态里 scan 档就是「mode = app、来源是扫描」(scanView)。
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import { scanOf } from './fixtures'

const WIN = { start: '2024-01-02', end: '2024-06-28' }

describe('view store · scan 档', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('scan 档就是 mode = app、来源是扫描;现算的 app 不是 scan 档', () => {
    const v = useViewStore()
    v.loadScanFile(scanOf(['AAPL']))
    expect([v.mode, v.appSource, v.scanView]).toEqual(['app', 'scan', true])
    v.enterLinked('app')
    expect([v.mode, v.appSource, v.scanView]).toEqual(['app', 'linked', false])
  })

  describe('进出 scan 时股票怎么带', () => {
    it('进:当前股票在扫描文件里,进 scan 后还是它', () => {
      const v = useViewStore()
      v.loadScanFile(scanOf(['AAPL', 'MSFT', 'NVDA']))
      v.openSymbol('MSFT')
      v.enterScan()
      expect([v.scanView, v.symbol]).toEqual([true, 'MSFT'])
    })

    it('进:当前股票不在扫描文件里,落到扫描列表上次停的那只', () => {
      const v = useViewStore()
      v.loadScanFile(scanOf(['AAPL', 'MSFT', 'NVDA']))
      v.selectSymbol('NVDA')            // 扫描列表停在 NVDA
      v.openSymbol('TSLA')              // 去标一只扫描里没有的
      v.enterScan()
      expect([v.scanView, v.symbol]).toEqual([true, 'NVDA'])
    })

    it('出:在 scan 里点过扫描列表的行 B,回前三档是 B', () => {
      const v = useViewStore()
      v.loadScanFile(scanOf(['AAPL', 'MSFT', 'NVDA']))
      v.openSymbol('TSLA')
      v.enterScan()
      v.selectSymbol('MSFT')
      v.enterAnnotate()
      expect([v.mode, v.symbol]).toEqual(['annotate', 'MSFT'])
    })

    it('出:没点过扫描列表的行,回到进 scan 前的 A(compare、现算的 app 同)', () => {
      const v = useViewStore()
      v.loadScanFile(scanOf(['AAPL', 'MSFT', 'NVDA']))
      v.openSymbol('TSLA')
      v.enterScan()
      expect(v.symbol).toBe('AAPL')     // 扫描列表停在第一行
      v.enterAnnotate()
      expect([v.mode, v.symbol]).toEqual(['annotate', 'TSLA'])
      v.enterScan()
      v.enterLinked('compare')
      expect([v.mode, v.symbol]).toEqual(['compare', 'TSLA'])
      v.enterScan()
      v.enterLinked('app')
      expect([v.mode, v.appSource, v.symbol]).toEqual(['app', 'linked', 'TSLA'])
    })

    it('出:从 no_scan 回去,也是 A', () => {
      const v = useViewStore()
      v.openSymbol('TSLA')
      v.enterScan()
      expect([v.noScan, v.symbol]).toEqual([true, null])
      v.enterAnnotate()
      expect([v.mode, v.symbol]).toEqual(['annotate', 'TSLA'])
    })

    it('在前三档点扫描列表的行:进到 scan 档看那只,回去也带着它', () => {
      const v = useViewStore()
      v.loadScanFile(scanOf(['AAPL', 'MSFT']))
      v.openSymbol('TSLA')
      v.selectSymbol('MSFT')
      expect([v.scanView, v.symbol]).toEqual([true, 'MSFT'])
      v.enterAnnotate()
      expect(v.symbol).toBe('MSFT')
    })

    it('进 scan 前没开着股票:回前三档时留着扫描里看的那只', () => {
      const v = useViewStore()
      v.loadScanFile(scanOf(['AAPL', 'MSFT']))
      v.enterAnnotate()
      expect([v.mode, v.symbol]).toEqual(['annotate', 'AAPL'])
    })

    it('加载扫描:从前三档加载、当前股票在这份扫描里就留着;不在就落在第一行;回去落在加载前那只', () => {
      const v = useViewStore()
      v.openSymbol('MSFT')
      v.loadScanFile(scanOf(['AAPL', 'MSFT']))
      expect([v.scanView, v.symbol]).toEqual([true, 'MSFT'])
      v.openSymbol('TSLA')
      v.loadScanFile(scanOf(['AAPL', 'MSFT']))
      expect(v.symbol).toBe('AAPL')
      v.enterAnnotate()
      expect(v.symbol).toBe('TSLA')
    })

    it('前三档之间切换照旧不换图', () => {
      const v = useViewStore()
      v.loadScanFile(scanOf(['AAPL', 'MSFT']))
      v.openSymbol('TSLA')
      v.enterLinked('compare')
      v.enterLinked('app')
      v.enterAnnotate()
      expect([v.mode, v.symbol]).toEqual(['annotate', 'TSLA'])
    })

    it('按代码打开离开 scan 档:落在给的那只,之后再进出 scan 按这次重新算', () => {
      const v = useViewStore()
      v.loadScanFile(scanOf(['AAPL', 'MSFT']))
      v.openSymbol('TSLA')
      v.enterScan()
      v.openSymbol('NFLX')
      expect([v.mode, v.symbol]).toEqual(['annotate', 'NFLX'])
      v.enterScan()
      v.enterAnnotate()
      expect(v.symbol).toBe('NFLX')
    })
  })

  describe('no_scan', () => {
    it('没加载扫描时进 scan:no_scan,股票不带过去', () => {
      const v = useViewStore()
      v.openSymbol('TSLA')
      v.enterScan()
      expect([v.mode, v.appSource, v.noScan, v.symbol]).toEqual(['app', 'scan', true, null])
    })

    it('在 scan 里删掉当前扫描:落到 no_scan;回去是进 scan 前那只,点过的行不算', () => {
      const v = useViewStore()
      v.openSymbol('TSLA')
      v.loadScanFile(scanOf(['AAPL', 'MSFT']))
      v.selectSymbol('MSFT')
      v.clearScanFile()
      expect([v.scanView, v.noScan, v.symbol]).toEqual([true, true, null])
      v.enterAnnotate()
      expect([v.mode, v.symbol]).toEqual(['annotate', 'TSLA'])
    })

    it('删掉扫描后再加载一份:扫描列表从第一行起,不带着删掉的那份停的位置', () => {
      const v = useViewStore()
      v.loadScanFile(scanOf(['AAPL', 'MSFT']))
      v.selectSymbol('MSFT')
      v.openSymbol('TSLA')
      v.clearScanFile()
      expect([v.mode, v.symbol]).toEqual(['annotate', 'TSLA'])   // 不在 scan 档:图不跟着清
      v.loadScanFile(scanOf(['NVDA', 'MSFT']))
      v.openSymbol('TSLA')
      v.enterScan()
      expect(v.symbol).toBe('NVDA')
    })

    it('回去落的那只股票(frontTierSymbol):no_scan 里是进 scan 前那只', () => {
      const v = useViewStore()
      v.openSymbol('TSLA')
      v.enterScan()
      expect(v.frontTierSymbol).toBe('TSLA')
      v.enterAnnotate()
      expect(v.frontTierSymbol).toBe('TSLA')
    })
  })

  describe('从扫描列表选股时清掉打开时给定的图窗', () => {
    it('拦:从扫描列表选股后切回 annotate,图窗不再停在上一只股票的日期段上', () => {
      const v = useViewStore()
      v.loadScanFile(scanOf(['AAPL', 'MSFT']))
      v.openSymbol('TSLA', WIN)
      v.selectSymbol('MSFT')
      expect(v.viewWindow).toBeNull()
      v.enterAnnotate()
      expect([v.symbol, v.viewWindow]).toEqual(['MSFT', null])
    })

    it('放:没选过扫描列表的行,回去还是打开时给定的图窗', () => {
      const v = useViewStore()
      v.loadScanFile(scanOf(['AAPL', 'MSFT']))
      v.openSymbol('TSLA', WIN)
      v.enterScan()
      v.enterAnnotate()
      expect([v.symbol, v.viewWindow]).toEqual(['TSLA', WIN])
    })
  })
})
